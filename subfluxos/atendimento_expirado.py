import json
import logging
import os
import httpx

logger = logging.getLogger(__name__)

CHATWOOT_URL = os.getenv("CHATWOOT_API_URL")
CHATWOOT_ACCOUNT_ID = os.getenv("CHATWOOT_ACCOUNT_ID", "1")
CHATWOOT_BASE_URL = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}"
NOTION_API_URL = "https://api.notion.com/v1"
DATABASE_ID_RECUPERACAO_VENDAS = os.getenv("DATABASE_ID_RECUPERACAO_VENDAS")
DATABASE_ID_CARDAPIO = os.getenv("DATABASE_ID_CARDAPIO")

TIMEOUT_HTTP = 15.0

# Mesma regra de expiração usada no SELECT e no UPDATE (única fonte da verdade)
_CONDICAO_EXPIRADA = """
    (EXTRACT(EPOCH FROM NOW()) - EXTRACT(EPOCH FROM ultima_interacao)) > 300
    AND is_bot_paused = FALSE
    AND estado_conversa != 'pagamento_concluido'
    AND estado_conversa != 'cliente_existe'
"""


async def _seguro(nome: str, coro, jid: str):
    """Isola um efeito externo: se falhar, registra no log e segue, sem derrubar o ciclo."""
    try:
        return await coro
    except Exception as e:
        logger.error("[%s] %s falhou: %s: %s", jid, nome, type(e).__name__, e)
        return None


async def processar_sessoes_expiradas(
    db_connection,
    notion_headers: dict,
    chatwoot_headers: dict,
    whatsapp_api_config: dict,
) -> dict:
    resultados_processamento = {"sessoes_encerradas": 0}

    sessoes_para_encerrar = await db_connection.fetch(f"""
        SELECT jid, carrinho_json, primeiro_nome, telefone_real, print_carrinho
        FROM conversas_bot
        WHERE {_CONDICAO_EXPIRADA}
        """)

    # Reset atômico: só zera se a sessão AINDA estiver expirada (o cliente pode
    # ter voltado a falar entre o SELECT e agora). RETURNING diz se "ganhamos" a sessão.
    sql_reset = f"""
        UPDATE conversas_bot
        SET estado_conversa = 'cliente_existe', cupom_promo = NULL, print_carrinho = NULL,
            carrinho_json = '[]', mapa_id_json = '{{}}', pagina_atual = 1, categoria_selecionada = NULL,
            expirando = FALSE, is_bot_paused = FALSE, valor_pedido = NULL
        WHERE jid = $1 AND {_CONDICAO_EXPIRADA}
        RETURNING jid
    """

    mensagem_fim = (
        "_*👸🏾 Kakaw - TheLordTrufas.*_\n\nSeu atendimento foi\nencerrado por falta de\ninteração. 😔\n\n"
        "Quando quiser, é só enviar\numa nova mensagem para\niniciar um novo atendimento 🥹🫶\n\n"
        "E claro, não esqueça\nde seguir a *@thelordtrufas*\nnas *Redes Sociais*.\n\n_#NãoResistaAoIrresistível😋🍫_"
    )

    for sessao_enc in sessoes_para_encerrar:
        jid = sessao_enc["jid"]
        try:
            carrinho_json_raw = sessao_enc["carrinho_json"]
            telefone_real = sessao_enc["telefone_real"]
            print_carrinho = sessao_enc["print_carrinho"]
            telefone_destino = telefone_real if telefone_real else jid

            try:
                carrinho_json = (
                    json.loads(carrinho_json_raw)
                    if isinstance(carrinho_json_raw, str)
                    else carrinho_json_raw
                )
            except Exception:
                carrinho_json = []

            # 1º: zera a sessão. Se algo falhar depois, a sessão já não é reprocessada
            #     (sem mensagem repetida a cada minuto e sem devolução dupla de estoque).
            reivindicada = await db_connection.fetchrow(sql_reset, jid)
            if not reivindicada:
                continue  # cliente voltou a interagir: não encerrar

            resultados_processamento["sessoes_encerradas"] += 1

            # 2º: efeitos externos, cada um isolado e com erro registrado no log
            await _seguro(
                "whatsapp",
                _enviar_whatsapp(telefone_destino, mensagem_fim, whatsapp_api_config),
                jid,
            )
            if carrinho_json and print_carrinho:
                await _seguro(
                    "estoque_notion",
                    _devolver_estoque_notion(carrinho_json, notion_headers),
                    jid,
                )
                await _seguro(
                    "carrinho_abandonado_notion",
                    _remover_carrinho_abandonado_notion(telefone_real, notion_headers),
                    jid,
                )
            await _seguro(
                "chatwoot",
                _limpar_chatwoot(telefone_real, jid, chatwoot_headers),
                jid,
            )

        except Exception as e:
            logger.error(
                "Erro ao encerrar sessão do JID %s: %s: %s", jid, type(e).__name__, e
            )

    return resultados_processamento


async def _enviar_whatsapp(destinatario: str, texto: str, config: dict):
    url = f"https://graph.facebook.com/v26.0/{config.get('phone_id')}/messages"
    headers = {
        "Authorization": f"Bearer {config.get('token')}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": destinatario,
        "type": "text",
        "text": {"preview_url": False, "body": texto},
    }
    async with httpx.AsyncClient(timeout=TIMEOUT_HTTP) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()  # 4xx/5xx da Meta agora aparecem no log


async def _devolver_estoque_notion(carrinho: list, notion_headers: dict):
    agrupados = {}
    for item in carrinho:
        item_id = item.get("id")
        if item_id:
            agrupados[item_id] = agrupados.get(item_id, 0) + int(item.get("qtd", 0))
        for sub in item.get("itens_internos", []):
            sub_id = sub.get("id")
            if sub_id:
                agrupados[sub_id] = agrupados.get(sub_id, 0) + int(sub.get("qtd", 1))

    async with httpx.AsyncClient(timeout=TIMEOUT_HTTP) as client:
        for item_id, qtd_devolver in agrupados.items():
            query_url = f"{NOTION_API_URL}/databases/{DATABASE_ID_CARDAPIO}/query"
            resp = await client.post(
                query_url,
                json={
                    "filter": {"property": "ID", "rich_text": {"equals": str(item_id)}}
                },
                headers=notion_headers,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if not results:
                logger.warning("Estoque: item %s não encontrado no cardápio", item_id)
                continue

            page_id = results[0]["id"]
            estoque_atual = (
                results[0].get("properties", {}).get("Estoque", {}).get("number", 0)
                or 0
            )
            resp_patch = await client.patch(
                f"{NOTION_API_URL}/pages/{page_id}",
                json={
                    "properties": {"Estoque": {"number": estoque_atual + qtd_devolver}}
                },
                headers=notion_headers,
            )
            resp_patch.raise_for_status()


async def _remover_carrinho_abandonado_notion(telefone: str, notion_headers: dict):
    if not telefone:
        return
    tel_num = int("".join(filter(str.isdigit, str(telefone))))
    async with httpx.AsyncClient(timeout=TIMEOUT_HTTP) as client:
        resp = await client.post(
            f"{NOTION_API_URL}/databases/{DATABASE_ID_RECUPERACAO_VENDAS}/query",
            json={"filter": {"property": "Whatsapp", "number": {"equals": tel_num}}},
            headers=notion_headers,
        )
        resp.raise_for_status()
        for page in resp.json().get("results", []):
            resp_patch = await client.patch(
                f"{NOTION_API_URL}/pages/{page['id']}",
                json={"archived": True},
                headers=notion_headers,
            )
            resp_patch.raise_for_status()


async def _limpar_chatwoot(telefone: str, jid: str, chatwoot_headers: dict):
    if not telefone and not jid:
        return
    search_query = telefone if telefone else jid
    async with httpx.AsyncClient(timeout=TIMEOUT_HTTP) as client:
        # params= faz o URL-encode (um "+" no telefone viraria espaço na query string)
        resp_busca = await client.get(
            f"{CHATWOOT_BASE_URL}/contacts/search",
            params={"q": search_query},
            headers=chatwoot_headers,
        )
        resp_busca.raise_for_status()
        source_id = None
        for c in resp_busca.json().get("payload", []):
            if inboxes := c.get("contact_inboxes", []):
                source_id = inboxes[0].get("source_id")
                break

        if not source_id:
            return
        resp_convs = await client.get(
            f"{CHATWOOT_BASE_URL}/conversations?status=open&assignee_type=me",
            headers=chatwoot_headers,
        )
        resp_convs.raise_for_status()
        for conv in resp_convs.json().get("data", {}).get("payload", []):
            msgs = conv.get("messages", [])
            if (
                msgs
                and msgs[0]
                .get("conversation", {})
                .get("contact_inbox", {})
                .get("source_id")
                == source_id
            ):
                conv_id = conv.get("id")
                r1 = await client.post(
                    f"{CHATWOOT_BASE_URL}/conversations/{conv_id}/assignments",
                    json={"assignee_id": 0},
                    headers=chatwoot_headers,
                )
                r1.raise_for_status()
                r2 = await client.post(
                    f"{CHATWOOT_BASE_URL}/conversations/{conv_id}/labels",
                    json={"labels": []},
                    headers=chatwoot_headers,
                )
                r2.raise_for_status()
                break
