import logging
import os
import secrets
import httpx

logger = logging.getLogger(__name__)

NOTION_TOKEN = os.getenv("NOTION_API_KEY", "SEU_NOTION_INTEGRATION_TOKEN")
HEADERS_NOTION = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}
DB_CLIENTES = "09ecc826e430417cbca704761420979b"
DB_RECUPERACAO_VENDAS = "00bbf526fa594184a47bbe954cb01d36"


def calcular_regras_giftback(valor_pedido: float) -> dict:
    if valor_pedido > 80.00:
        return {"desconto": 10, "minimo": 80.00, "validade": 30}
    elif valor_pedido > 40.00:
        return {"desconto": 7, "minimo": 40.00, "validade": 20}
    elif valor_pedido > 25.00:
        return {"desconto": 5, "minimo": 25.00, "validade": 14}
    return {"desconto": 0, "minimo": 0.00, "validade": 0}


async def buscar_cliente_notion(telefone_real: str) -> str:
    url = f"https://api.notion.com/v1/databases/{DB_CLIENTES}/query"
    payload = {
        "filter": {"property": "Whatsapp", "rich_text": {"equals": str(telefone_real)}}
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=HEADERS_NOTION, json=payload)
        results = response.json().get("results", [])
        return results[0].get("id") if results else None


async def atualizar_cliente_notion(cliente_id: str, codigo_gift: str, desconto: int):
    url = f"https://api.notion.com/v1/pages/{cliente_id}"
    payload = {
        "properties": {
            "Giftback": {
                "rich_text": [{"text": {"content": codigo_gift.upper()}}]
            },
            "Desconto": {"number": desconto},
            "CRM": {"status": {"name": "Cliente"}},
        }
    }
    async with httpx.AsyncClient() as client:
        await client.patch(url, headers=HEADERS_NOTION, json=payload)


async def limpar_recuperacao_vendas_notion(telefone_real: str):
    url = f"https://api.notion.com/v1/databases/{DB_RECUPERACAO_VENDAS}/query"
    payload = {
        "filter": {
            "and": [
                {
                    "property": "Whatsapp",
                    "number": {
                        "equals": (
                            float(telefone_real) if str(telefone_real).isdigit() else 0
                        )
                    },
                },
                {"property": "Enviado", "checkbox": {"equals": True}},
            ]
        }
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=HEADERS_NOTION, json=payload)
        for page in response.json().get("results", []):
            await client.patch(
                f"https://api.notion.com/v1/pages/{page.get('id')}",
                headers=HEADERS_NOTION,
                json={"archived": True},
            )


async def processar_finalizacao_pedido(payload_fila: dict, db_connection=None) -> dict:
    numero_pedido = payload_fila.get("numero_pedido")
    telefone_real = payload_fila.get("telefone_real")

    if not numero_pedido or not telefone_real:
        return {"status": "erro", "mensagem": "Dados insuficientes."}

    sql_busca = "SELECT jid, primeiro_nome, valor_total FROM pedidos WHERE numero_pedido = $1 AND telefone_real = $2 LIMIT 1;"
    pedido_info = None
    if db_connection:
        pedido_info = await db_connection.fetchrow(
            sql_busca, numero_pedido, telefone_real
        )

    if not pedido_info:
        return {"status": "erro", "mensagem": "Pedido não encontrado."}

    jid, primeiro_nome, valor_total = (
        pedido_info["jid"],
        pedido_info.get("primeiro_nome", "Cliente"),
        float(pedido_info.get("valor_total", 0.0)),
    )

    if db_connection:
        await db_connection.execute(
            "UPDATE pedidos SET status_pedido = 'ENTREGUE' WHERE numero_pedido = $1 AND telefone_real = $2;",
            numero_pedido,
            telefone_real,
        )

    regras_gb = calcular_regras_giftback(valor_total)
    codigo_gift = secrets.token_hex(4).upper()

    cliente_notion_id = await buscar_cliente_notion(telefone_real)
    if cliente_notion_id:
        await atualizar_cliente_notion(
            cliente_notion_id, codigo_gift, regras_gb["desconto"]
        )
    await limpar_recuperacao_vendas_notion(telefone_real)

    msg_entrega = f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_*{primeiro_nome}*_,\n\nO pedido *TLF-{numero_pedido}* foi\nentregue com sucesso!!! 🛵🛍️\n\nObrigado por comprar\nna *TheLordTrufas*! 🤗🤎\n\nSiga a *@thelordtrufas*\nnas *Redes Sociais*.\n\n-------------------------------------------------------\n\n_⚠️ Se tiver algum problema_\n_com seu pedido, basta_\n_iniciar uma nova conversa_\n_e selecionar a opção_\n_*AJUDA* no *Menu Principal* ⚠️_\n\n_#NãoResistaAoIrresistível😋🍫_\nㅤ"
    msg_giftback = f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_*{primeiro_nome}*_,\n\nVocê ganhou um *Giftback* \npara utilizar na sua \npróxima compra!!! 🎁😍\n\nUtilize o CUPOM: *{codigo_gift}* \nna sua próxima compra e \ntenha _*{regras_gb['desconto']}%*_ de desconto!!!\n\nEsse *CUPOM* é *CÁLIDO* (Válido)\npor _*{regras_gb['validade']}*_ dias, e poderá\nser usado apenas uma *ÚNICA VEZ*\nem compras *ACIMA* de _*R${regras_gb['minimo']:.2f}*_.\n\n_⚠️*Atenção:* O desconto *NÃO*_\n_é aplicado no *FRETE*⚠️_\n\n-------------------------------------------------------\n\nSiga a *@thelordtrufas*\nnas *Redes Sociais*:\nㅤ"

    sql_updates = [
        f"UPDATE conversas_bot SET data_compra = NOW(), is_bot_paused = FALSE WHERE jid = '{jid}';",
        f"UPDATE pedidos SET status_pedido = 'AVALIACAO' WHERE numero_pedido = '{numero_pedido}' AND jid = '{jid}';",
    ]

    return {
        "sql_update": sql_updates,
        "mensagens_multiplas": [
            {"type": "text", "text": {"body": msg_entrega}},
            {"type": "text", "text": {"body": msg_giftback}},
        ],
    }
