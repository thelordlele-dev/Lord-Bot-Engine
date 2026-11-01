import json
import logging
import os
import httpx

logger = logging.getLogger(__name__)

# Monta o URL completo da API do Chatwoot usando a sua variável correta
CHATWOOT_URL = os.getenv("CHATWOOT_API_URL")
CHATWOOT_ACCOUNT_ID = os.getenv("CHATWOOT_ACCOUNT_ID", "1")
CHATWOOT_BASE_URL = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}"

NOTION_API_URL = "https://api.notion.com/v1"
DATABASE_ID_RECUPERACAO_VENDAS = os.getenv("DATABASE_ID_RECUPERACAO_VENDAS")
DATABASE_ID_CARDAPIO = os.getenv("DATABASE_ID_CARDAPIO")


async def processar_pagamentos_expirados(
    db_connection,
    notion_headers: dict,
    chatwoot_headers: dict,
    whatsapp_api_config: dict,
) -> dict:
    resultados_processamento = {"pedidos_cancelados": 0}

    query_expirados = """
        SELECT jid, carrinho_json, primeiro_nome, telefone_real, print_carrinho 
        FROM conversas_bot 
        WHERE (EXTRACT(EPOCH FROM NOW()) - EXTRACT(EPOCH FROM ultima_interacao)) > 1800 
          AND is_bot_paused = TRUE 
          AND estado_conversa = 'aguardando_pagamento'
    """
    sessoes = await db_connection.fetch(query_expirados)

    for sessao in sessoes:
        jid, carrinho_json_raw, primeiro_nome = (
            sessao["jid"],
            sessao["carrinho_json"],
            sessao["primeiro_nome"],
        )
        telefone_real, print_carrinho = (
            sessao["telefone_real"],
            sessao["print_carrinho"],
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

        mensagem_cancelamento = (
            f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\nSeu pedido foi *CANCELADO*\n"
            f"por falta de *PAGAMENTO*. 😔\n\nQuando quiser, é só enviar\numa nova mensagem para\n"
            f"iniciar um novo atendimento 🥹🫶\n\nE claro, não esqueça\nde seguir a *@thelordtrufas*\n"
            f"nas *Redes Sociais*.\n\n_#NãoResistaAoIrresistível😋🍫_"
        )
        await _enviar_whatsapp(
            telefone_destino, mensagem_cancelamento, whatsapp_api_config
        )

        if carrinho_json and print_carrinho:
            await _devolver_estoque_notion(carrinho_json, notion_headers)
            await _remover_carrinho_abandonado_notion(telefone_real, notion_headers)

        sql_reset = """
            UPDATE conversas_bot SET estado_conversa = 'cliente_existe', print_carrinho = NULL, 
            carrinho_json = '[]', mapa_id_json = '{}', cupom_promo = NULL, pagina_atual = 1, 
            categoria_selecionada = NULL, expirando = FALSE, is_bot_paused = FALSE, valor_pedido = NULL 
            WHERE jid = $1
        """
        await db_connection.execute(sql_reset, jid)
        await _limpar_chatwoot(telefone_real, jid, chatwoot_headers)

        resultados_processamento["pedidos_cancelados"] += 1

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
            resp = await client.post(
                f"{NOTION_API_URL}/databases/{DATABASE_ID_CARDAPIO}/query",
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
                f"{NOTION_API_URL}/databases/{DATABASE_ID_RECUPERACAO_VENDAS}/query",
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
        logger.error("Erro Notion: %s", e)


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
