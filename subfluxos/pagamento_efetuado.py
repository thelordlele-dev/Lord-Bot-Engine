from datetime import datetime
import json
import logging
import os
import httpx

logger = logging.getLogger(__name__)
NOTION_TOKEN = os.getenv("NOTION_API_KEY", "")
HEADERS_NOTION = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

DB_FLUXO_CAIXA = "2367a7a879af80e2837ac574f098c30f"
DB_FATURAMENTO = "2367a7a879af8090b753f153653e59ab"
DB_CLIENTES = "09ecc826e430417cbca704761420979b"
DB_CUPONS = "2897a7a879af804891d7fc0db15b20c0"


def formatar_carrinho_em_linha(carrinho_json) -> str:
    if (
        not carrinho_json
        or not isinstance(carrinho_json, list)
        or len(carrinho_json) == 0
    ):
        return "Carrinho vazio"
    return "\n\n".join(
        [f"{item.get('qtd', 0)}x - {item.get('nome', '')}" for item in carrinho_json]
    )


async def buscar_faturamento_dia_notion() -> str:
    url = f"https://api.notion.com/v1/databases/{DB_FATURAMENTO}/query"
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=HEADERS_NOTION, json={})
        results = response.json().get("results", [])
        return results[0].get("id") if results else None


async def buscar_cliente_notion(telefone_real: str) -> str:
    url = f"https://api.notion.com/v1/databases/{DB_CLIENTES}/query"
    payload = {
        "filter": {"property": "Whatsapp", "rich_text": {"equals": str(telefone_real)}}
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=HEADERS_NOTION, json=payload)
        results = response.json().get("results", [])
        return results[0].get("id") if results else None


async def criar_registro_fluxo_caixa(
    dados: dict, faturamento_id: str, cliente_id: str
) -> str:
    properties = {
        "Descrição": {"title": [{"text": {"content": dados["descricao"]}}]},
        "Data": {"date": {"start": dados["data"]}},
        "Quantidade Vendida": {"number": dados["qtde_vendida"]},
        "Valor Total": {"number": dados["valor_total"]},
        "Canal": {"select": {"name": dados["canal"]}},
    }
    if faturamento_id:
        properties["Faturamento"] = {"relation": [{"id": faturamento_id}]}
    if cliente_id:
        properties["Clientes"] = {"relation": [{"id": cliente_id}]}

    payload = {
        "parent": {"database_id": DB_FLUXO_CAIXA},
        "properties": properties,
        "children": [
            {
                "object": "block",
                "heading_3": {
                    "rich_text": [{"text": {"content": dados["carrinho_texto"]}}]
                },
            }
        ],
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.notion.com/v1/pages", headers=HEADERS_NOTION, json=payload
        )
        return response.json().get("id") if response.status_code == 200 else None


async def vincular_cupom_notion(cupom_codigo: str, id_fluxo_caixa: str):
    url = f"https://api.notion.com/v1/databases/{DB_CUPONS}/query"
    payload = {"filter": {"property": "Cupom", "title": {"equals": str(cupom_codigo)}}}
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=HEADERS_NOTION, json=payload)
        results = response.json().get("results", [])
        if results:
            page_id = results[0].get("id")
            await client.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers=HEADERS_NOTION,
                json={
                    "properties": {
                        "Fluxo de Caixa": {
                            "relation": [{"id": id_fluxo_caixa}]
                        }
                    }
                },
            )


async def processar_pagamento_efetuado(payload_fila: dict, db_connection=None) -> dict:
    numero_pedido = payload_fila.get("numero_pedido")
    telefone_real = payload_fila.get("telefone_real") or payload_fila.get("source_id")

    if not numero_pedido:
        return {"status": "erro", "mensagem": "Número do pedido ausente."}

    sql_verifica_pedido = "SELECT * FROM pedidos WHERE status_pedido = 'PAGAMENTO_APROVADO' AND numero_pedido = $1 AND (telefone_real = $2 OR jid = $2) LIMIT 1;"
    data_compra, valor_compra, cupom_promo, jid, carrinho_json = (
        datetime.utcnow().isoformat() + "Z",
        0.0,
        None,
        None,
        [],
    )

    if db_connection:
        resultado_pedido = await db_connection.fetchrow(
            sql_verifica_pedido, numero_pedido, telefone_real
        )
        if resultado_pedido:
            data_compra = str(resultado_pedido.get("data_criacao", data_compra))
            valor_compra = float(resultado_pedido.get("valor_total", 0.0))
            cupom_promo = resultado_pedido.get("cupom_promo")
            jid = resultado_pedido.get("jid")
            carrinho_raw = resultado_pedido.get("carrinho_json", [])
            try:
                carrinho_json = (
                    json.loads(carrinho_raw)
                    if isinstance(carrinho_raw, str)
                    else carrinho_raw
                )
            except Exception:
                carrinho_json = []
        else:
            return {"status": "erro", "mensagem": "Pedido aprovado não encontrado."}

    carrinho_formatado = formatar_carrinho_em_linha(carrinho_json)
    qtde_total_itens = sum(item.get("qtd", 0) for item in carrinho_json)

    faturamento_id = await buscar_faturamento_dia_notion()
    cliente_id = await buscar_cliente_notion(telefone_real)

    id_caixa_criado = await criar_registro_fluxo_caixa(
        {
            "descricao": f"TLF-{numero_pedido}",
            "data": data_compra,
            "qtde_vendida": qtde_total_itens,
            "valor_total": valor_compra,
            "carrinho_texto": carrinho_formatado,
            "canal": "WhatsApp",
        },
        faturamento_id,
        cliente_id,
    )

    if cupom_promo and cupom_promo != "null" and id_caixa_criado:
        await vincular_cupom_notion(cupom_promo, id_caixa_criado)

    sql_reseta_cliente = "UPDATE conversas_bot SET print_carrinho = NULL, estado_conversa = 'cliente_existe', carrinho_json = '[]'::jsonb, mapa_id_json = '{}'::jsonb, pagina_atual = 1, categoria_selecionada = NULL, expirando = FALSE, valor_pedido = NULL, ultima_interacao = NOW(), is_bot_paused = TRUE WHERE jid = $1"
    if db_connection and jid:
        await db_connection.execute(sql_reseta_cliente, jid)

    return {
        "status": "sucesso",
        "numero_pedido": numero_pedido,
        "qtde_itens": qtde_total_itens,
        "notion_fluxo_id": id_caixa_criado,
    }
