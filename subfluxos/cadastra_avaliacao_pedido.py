import logging
import os
import httpx

logger = logging.getLogger(__name__)

NOTION_TOKEN = os.getenv("NOTION_API_KEY", "SEU_NOTION_INTEGRATION_TOKEN")
HEADERS_NOTION = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}
DATABASE_ID_FLUXO_CAIXA = os.getenv("DATABASE_ID_FLUXO_CAIXA", "")


async def atualizar_avaliacao_notion(
    numero_pedido: str, nota_estrelas: str, comentario: str
) -> bool:
    url_query = f"https://api.notion.com/v1/databases/{DATABASE_ID_FLUXO_CAIXA}/query"
    payload_query = {
        "filter": {"property": "Descrição", "title": {"equals": f"TLF-{numero_pedido}"}}
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url_query, headers=HEADERS_NOTION, json=payload_query
        )
        results = response.json().get("results", [])
        if not results:
            return False

        page_id = results[0].get("id")
        payload_update = {
            "properties": {
                "Avaliação": {"select": {"name": nota_estrelas}},
                "Comentário": {"rich_text": [{"text": {"content": comentario or ""}}]},
            }
        }
        await client.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=HEADERS_NOTION,
            json=payload_update,
        )
        return True


async def processar_cadastro_avaliacao(payload_flow: dict, db_connection=None) -> dict:
    nota = str(payload_flow.get("screen_0_D_sua_nota_0", "5")).strip()
    comentario = payload_flow.get("screen_0_Comentrio_1", "")
    jid = payload_flow.get("Jid")

    if not jid:
        return {"status": "erro", "mensagem": "JID do cliente ausente."}

    mapa_estrelas = {
        "1": "⭐",
        "2": "⭐⭐",
        "3": "⭐⭐⭐",
        "4": "⭐⭐⭐⭐",
        "5": "⭐⭐⭐⭐⭐",
    }
    estrelas_formatadas = mapa_estrelas.get(nota, "⭐⭐⭐⭐⭐")

    sql_busca_pedido = """
        SELECT numero_pedido, jid, telefone_real 
        FROM pedidos 
        WHERE jid = $1 AND status_pedido = 'AVALIANDO' 
        ORDER BY numero_pedido DESC LIMIT 1;
    """

    pedido_info = None
    if db_connection:
        pedido_info = await db_connection.fetchrow(sql_busca_pedido, jid)

    if not pedido_info:
        return {"status": "erro", "mensagem": "Pedido pendente não encontrado."}

    numero_pedido = pedido_info["numero_pedido"]
    telefone_real = pedido_info["telefone_real"]

    await atualizar_avaliacao_notion(numero_pedido, estrelas_formatadas, comentario)

    novo_status = "FINALIZADO" if nota == "4" else "CONCLUIDO"
    if db_connection:
        await db_connection.execute(
            "UPDATE pedidos SET status_pedido = $1 WHERE jid = $2 AND numero_pedido = $3",
            novo_status,
            jid,
            numero_pedido,
        )

    return {
        "sql_update": None,  # (Não precisa de SQL aqui porque já foi executado acima)
    }
