import json
import logging
import os
import httpx

logger = logging.getLogger(__name__)

CHATWOOT_URL = os.getenv("CHATWOOT_API_URL")
CHATWOOT_ACCOUNT_ID = os.getenv("CHATWOOT_ACCOUNT_ID", "1")
CHATWOOT_BASE_URL = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}"
NOTION_API_URL = "https://api.notion.com/v1"


async def processar_sessoes_expiradas(
    db_connection,
    notion_headers: dict,
    chatwoot_headers: dict,
    whatsapp_api_config: dict,
) -> dict:
    resultados_processamento = {"avisos_enviados": 0, "sessoes_encerradas": 0}

    # VERIFICAÇÃO BLINDADA COM EPOCH (Segundos) PARA EVITAR BUG DE TIMEZONE
    # 20 minutos = 1200 segundos
    query_aviso = """
        SELECT jid, carrinho_json, primeiro_nome, telefone_real, expirando 
        FROM conversas_bot 
        WHERE (EXTRACT(EPOCH FROM NOW()) - EXTRACT(EPOCH FROM ultima_interacao)) > 1200 
          AND is_bot_paused = FALSE 
          AND estado_conversa != 'pagamento_concluido' 
          AND estado_conversa != 'cliente_existe'
    """
    sessoes_para_aviso = await db_connection.fetch(query_aviso)

    for sessao in sessoes_para_aviso:
        jid, primeiro_nome, telefone_real, expirando = (
            sessao["jid"],
            sessao["primeiro_nome"],
            sessao["telefone_real"],
            sessao["expirando"],
        )
        telefone_destino = telefone_real if telefone_real else jid

        if not expirando:
            mensagem_aviso = (
                f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_{primeiro_nome}_,\nvocê ainda está aí?\n\n"
                f"Caso não haja interação nos\npróximos *10 MINUTOS* seu\n"
                f"atendimento será *ENCERRADO* automático. 😕"
            )
            await _enviar_whatsapp(
                telefone_destino, mensagem_aviso, whatsapp_api_config
            )
            await db_connection.execute(
                "UPDATE conversas_bot SET expirando = TRUE WHERE jid = $1", jid
            )
            resultados_processamento["avisos_enviados"] += 1

    # 30 minutos = 1800 segundos
    query_encerramento = """
        SELECT jid, carrinho_json, primeiro_nome, telefone_real, print_carrinho 
        FROM conversas_bot 
        WHERE (EXTRACT(EPOCH FROM NOW()) - EXTRACT(EPOCH FROM ultima_interacao)) > 1800 
          AND is_bot_paused = FALSE 
          AND estado_conversa != 'pagamento_concluido' 
          AND estado_conversa != 'cliente_existe'
    """
    sessoes_para_encerrar = await db_connection.fetch(query_encerramento)

    for sessao_enc in sessoes_para_encerrar:
        jid, carrinho_json_raw, primeiro_nome = (
            sessao_enc["jid"],
            sessao_enc["carrinho_json"],
            sessao_enc["primeiro_nome"],
        )
        telefone_real, print_carrinho = (
            sessao_enc["telefone_real"],
            sessao_enc["print_carrinho"],
        )
        telefone_destino = telefone_real if telefone_real else jid

        try:
            carrinho_json = (
                json.loads(carrinho_json_raw)
                if isinstance(carrinho_json_raw, str)
                else carrinho_json_raw
            )
        except Exception:
            carrinho_json = []

        mensagem_fim = (
            f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\nSeu atendimento foi\nencerrado por falta de\ninteração. 😔\n\n"
            f"Quando quiser, é só enviar\numa nova mensagem para\niniciar um novo atendimento 🥹🫶\n\n"
            f"E claro, não esqueça\nde seguir a *@thelordtrufas*\nnas *Redes Sociais*.\n\n_#NãoResistaAoIrresistível😋🍫_"
        )
        await _enviar_whatsapp(telefone_destino, mensagem_fim, whatsapp_api_config)

        if carrinho_json and print_carrinho:
            await _devolver_estoque_notion(carrinho_json, notion_headers)
            await _remover_carrinho_abandonado_notion(telefone_real, notion_headers)

        # Usando casting seguro para JSONB compatível com asyncpg
        sql_reset = """
            UPDATE conversas_bot 
            SET estado_conversa = 'cliente_existe', cupom_promo = NULL, print_carrinho = NULL, 
                carrinho_json = '[]', mapa_id_json = '{}', pagina_atual = 1, categoria_selecionada = NULL, 
                expirando = FALSE, is_bot_paused = FALSE, valor_pedido = NULL 
            WHERE jid = $1
        """
        await db_connection.execute(sql_reset, jid)
        await _limpar_chatwoot(telefone_real, jid, chatwoot_headers)

        resultados_processamento["sessoes_encerradas"] += 1

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
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload, headers=headers)


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

    async with httpx.AsyncClient() as client:
        for item_id, qtd_devolver in agrupados.items():
            query_url = (
                f"{NOTION_API_URL}/databases/0ce7b9883c49441eb6852a69e6894667/query"
            )
            resp = await client.post(
                query_url,
                json={
                    "filter": {"property": "ID", "rich_text": {"equals": str(item_id)}}
                },
                headers=notion_headers,
            )
            results = resp.json().get("results", [])
            if results:
                page_id = results[0]["id"]
                estoque_atual = (
                    results[0].get("properties", {}).get("Estoque", {}).get("number", 0)
                    or 0
                )
                await client.patch(
                    f"{NOTION_API_URL}/pages/{page_id}",
                    json={
                        "properties": {
                            "Estoque": {"number": estoque_atual + qtd_devolver}
                        }
                    },
                    headers=notion_headers,
                )


async def _remover_carrinho_abandonado_notion(telefone: str, notion_headers: dict):
    if not telefone:
        return
    try:
        tel_num = int("".join(filter(str.isdigit, str(telefone))))
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{NOTION_API_URL}/databases/00bbf526fa594184a47bbe954cb01d36/query",
                json={
                    "filter": {"property": "Whatsapp", "number": {"equals": tel_num}}
                },
                headers=notion_headers,
            )
            for page in resp.json().get("results", []):
                await client.patch(
                    f"{NOTION_API_URL}/pages/{page['id']}",
                    json={"archived": True},
                    headers=notion_headers,
                )
    except Exception as e:
        logger.error(f"Erro Notion: {e}")


async def _limpar_chatwoot(telefone: str, jid: str, chatwoot_headers: dict):
    if not telefone and not jid:
        return
    search_query = telefone if telefone else jid
    async with httpx.AsyncClient() as client:
        resp_busca = await client.get(
            f"{CHATWOOT_BASE_URL}/contacts/search?q={search_query}",
            headers=chatwoot_headers,
        )
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
                await client.post(
                    f"{CHATWOOT_BASE_URL}/conversations/{conv_id}/assignments",
                    json={"assignee_id": 0},
                    headers=chatwoot_headers,
                )
                await client.post(
                    f"{CHATWOOT_BASE_URL}/conversations/{conv_id}/labels",
                    json={"labels": []},
                    headers=chatwoot_headers,
                )
                break
