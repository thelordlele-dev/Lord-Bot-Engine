import os
import json
import logging
import httpx

logger = logging.getLogger(__name__)

NOTION_API_URL = "https://api.notion.com/v1"
DATABASE_ID_CARDAPIO = os.getenv("DATABASE_ID_CARDAPIO")
NOTION_TOKEN = os.getenv("NOTION_API_KEY", "")


async def processar_encerramento_sessao(
    jid: str, telefone_real: str, primeiro_nome: str, carrinho_json, motivo: str
) -> dict:
    logger.info(f"Processando encerramento | JID: {jid} | Motivo: {motivo}")

    notion_headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    try:
        carrinho_lista = (
            json.loads(carrinho_json)
            if isinstance(carrinho_json, str)
            else carrinho_json
        )
    except Exception:
        carrinho_lista = []

    if carrinho_lista:
        agrupados = {}
        for item in carrinho_lista:
            if item_id := item.get("id"):
                agrupados[item_id] = agrupados.get(item_id, 0) + int(item.get("qtd", 0))
            for sub in item.get("itens_internos", []):
                if sub_id := sub.get("id"):
                    agrupados[sub_id] = agrupados.get(sub_id, 0) + int(
                        sub.get("qtd", 0)
                    )

        if agrupados:
            async with httpx.AsyncClient() as client:
                for item_id, qtd_a_devolver in agrupados.items():
                    query_url = f"{NOTION_API_URL}/databases/{DATABASE_ID_CARDAPIO}/query"
                    resp_query = await client.post(
                        query_url,
                        json={
                            "filter": {
                                "property": "ID",
                                "rich_text": {"equals": str(item_id)},
                            }
                        },
                        headers=notion_headers,
                    )
                    results = resp_query.json().get("results", [])
                    if results:
                        page_id = results[0]["id"]
                        estoque_atual = (
                            results[0]
                            .get("properties", {})
                            .get("Estoque", {})
                            .get("number", 0)
                            or 0
                        )
                        await client.patch(
                            f"{NOTION_API_URL}/pages/{page_id}",
                            json={
                                "properties": {
                                    "Estoque": {
                                        "number": estoque_atual + qtd_a_devolver
                                    }
                                }
                            },
                            headers=notion_headers,
                        )

    if motivo == "sair":
        texto_mensagem = (
            f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_*{primeiro_nome}*_, \n"
            f"obrigado pela visita!\nEsperamos que volte logo\npara saborear uma de\n"
            f"nossas deliciosas \n*Trufas de Colher* 🤗.\n\nE claro, não esqueça\n"
            f"de seguir a *@thelordtrufas*\nnas Redes Sociais! 👋🤎\n\n\n_Atendimento Encerrado._"
        )
    elif motivo == "inatividade":
        texto_mensagem = (
            f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\nSeu atendimento foi\nencerrado por falta de\ninteração. 😔\n\n"
            f"Quando quiser, é só enviar\numa nova mensagem para\niniciar um novo atendimento 🥹🫶\n\n"
            f"E claro, não esqueça\nde seguir a *@thelordtrufas*\nnas *Redes Sociais*.\n\n_#NãoResistaAoIrresistível😋🍫_"
        )
    elif motivo == "pagamento_expirado":
        texto_mensagem = (
            f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\nSeu pedido foi *CANCELADO*\n"
            f"por falta de *PAGAMENTO*. 😔\n\nQuando quiser, é só enviar\numa nova mensagem para\n"
            f"iniciar um novo atendimento 🥹🫶\n\nE claro, não esqueça\nde seguir a *@thelordtrufas*\n"
            f"nas *Redes Sociais*.\n\n_#NãoResistaAoIrresistível😋🍫_"
        )
    else:
        texto_mensagem = "_Atendimento encerrado._"

    sql_update = f"""
        UPDATE conversas_bot 
        SET estado_conversa = 'cliente_existe', cupom_promo = NULL, print_carrinho = NULL, 
            carrinho_json = '[]'::jsonb, mapa_id_json = '{{}}'::jsonb, pagina_atual = 1, 
            categoria_selecionada = NULL, expirando = FALSE, is_bot_paused = FALSE, 
            valor_pedido = NULL, ultima_interacao = NOW() 
        WHERE jid = '{jid}';
    """

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": telefone_real,
        "type": "text",
        "text": {"preview_url": False, "body": texto_mensagem},
    }

    return {"sql_update": sql_update, "payload": payload}
