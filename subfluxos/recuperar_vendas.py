from datetime import datetime, timezone
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
DATABASE_ID_RECUPERACAO_VENDAS = os.getenv("DATABASE_ID_RECUPERACAO_VENDAS")


async def buscar_carrinhos_abandonados_notion() -> list:
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID_RECUPERACAO_VENDAS}/query"
    payload = {
        "filter": {"property": "Recuperar", "formula": {"checkbox": {"equals": True}}}
    }
    carrinhos = []
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=HEADERS_NOTION, json=payload)
        if response.status_code == 200:
            for page in response.json().get("results", []):
                props = page.get("properties", {})
                whatsapp_prop = props.get("Whatsapp", {}).get("number")
                carrinho_texto = "".join(
                    [
                        t.get("plain_text", "")
                        for t in props.get("Carrinho", {}).get("rich_text", [])
                    ]
                )
                abandono_prop = props.get("Abandono", {}).get("date", {})
                if whatsapp_prop:
                    carrinhos.append(
                        {
                            "page_id": page.get("id"),
                            "whatsapp": str(int(whatsapp_prop)),
                            "carrinho": carrinho_texto,
                            "data_abandono": (
                                abandono_prop.get("start") if abandono_prop else None
                            ),
                        }
                    )
    return carrinhos


async def marcar_como_enviado_notion(page_id: str):
    async with httpx.AsyncClient() as client:
        await client.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=HEADERS_NOTION,
            json={"properties": {"Enviado": {"checkbox": True}}},
        )


async def enviar_mensagem_whatsapp(
    destinatario: str, texto: str, whatsapp_config: dict
) -> bool:
    if not whatsapp_config or not destinatario:
        return False
    url = f"https://graph.facebook.com/v26.0/{whatsapp_config.get('WHATSAPP_PHONE_NUMBER_ID')}/messages"
    headers = {
        "Authorization": f"Bearer {whatsapp_config.get('token')}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": destinatario,
        "type": "text",
        "text": {"body": texto},
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        return response.status_code in [200, 201]


async def processar_recuperacao_vendas(
    db_connection=None, whatsapp_config: dict = None
) -> dict:
    carrinhos = await buscar_carrinhos_abandonados_notion()
    if not carrinhos:
        return {"recuperados_enviados": 0}

    hoje_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    enviados = 0

    for item in carrinhos:
        whatsapp_num = item["whatsapp"]
        data_formatada = "recentemente"
        if item["data_abandono"]:
            try:
                data_formatada = (
                    datetime.fromisoformat(
                        item["data_abandono"].replace("Z", "+00:00")
                    ).strftime("%d/%m/%Y %H:%M")
                    + "h"
                )
            except Exception:
                pass

        cliente_info = None
        if db_connection:
            cliente_info = await db_connection.fetchrow(
                "SELECT primeiro_nome, telefone_real, jid, ultima_interacao FROM conversas_bot WHERE jid = $1 OR telefone_real = $1 LIMIT 1;",
                whatsapp_num,
            )

        if not cliente_info or (
            cliente_info.get("ultima_interacao")
            and str(cliente_info.get("ultima_interacao")).split(" ")[0] == hoje_str
        ):
            continue

        primeiro_nome = cliente_info.get("primeiro_nome", "Cliente")
        msg = f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\nOii *{primeiro_nome}*,\ntudo bem? 😃\n\nNo dia *{data_formatada}*\nvocê acabou deixando\num *Carrinho* para trás 🥹\n\nConfira 👀:\n\n{item['carrinho']}\n\n----------------------------------------------------------\n\nA _*TheLordTrufas*_ está ansiosa\nesperando você voltar, para\nsaborear nossas deliciosas\ntrufas de colher, a sobremesa\nperfeita para todos os momentos!!! 🍫✨\n\n_#NãoResistaAoIrresistível😋🍫_"

        if await enviar_mensagem_whatsapp(
            cliente_info.get("telefone_real") or whatsapp_num, msg, whatsapp_config
        ):
            await marcar_como_enviado_notion(item["page_id"])
            enviados += 1

    return {"recuperados_enviados": enviados}
