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
DATABASE_ID_PRECOS_VENDA = os.getenv("DATABASE_ID_PRECOS_VENDA")


async def buscar_promocoes_expiradas_notion() -> list:
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID_PRECOS_VENDA}/query"
    payload = {
        "filter": {
            "property": "Promo Expirou?",
            "formula": {"checkbox": {"equals": True}},
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=HEADERS_NOTION, json=payload)
        return [
            page["id"] for page in response.json().get("results", []) if page.get("id")
        ]


async def atualizar_produto_para_normal_notion(page_id: str) -> bool:
    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {
        "properties": {
            "Status": {"select": {"name": "Normal"}},
            "%OFF": {"number": None},
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.patch(url, headers=HEADERS_NOTION, json=payload)
        return response.status_code in [200, 201]


async def processar_atualizacao_promocoes() -> dict:
    paginas_expiradas = await buscar_promocoes_expiradas_notion()
    if not paginas_expiradas:
        return {"status": "sucesso", "promocoes_atualizadas": 0}

    atualizados_count = 0
    for page_id in paginas_expiradas:
        if await atualizar_produto_para_normal_notion(page_id):
            atualizados_count += 1

    return {"status": "sucesso", "promocoes_atualizadas": atualizados_count}
