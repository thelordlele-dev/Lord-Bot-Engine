from datetime import datetime, timezone, timedelta
import json
import logging
import httpx

logger = logging.getLogger(__name__)


def formatar_carrinho_em_linha(carrinho_json) -> str:
    if (
        not carrinho_json
        or not isinstance(carrinho_json, list)
        or len(carrinho_json) == 0
    ):
        return "Carrinho vazio"
    return " | ".join(
        [
            f"{item.get('qtd', 0)}x {item.get('nome', '')} - {item.get('precoUnitario', 0)}"
            for item in carrinho_json
        ]
    )


async def processar_criacao_pagamento(payload_fila: dict, db_connection) -> dict:
    telefone_real = payload_fila.get("telefone_real")
    numero_pedido = payload_fila.get("numero_pedido")
    jid = payload_fila.get("Jid")

    if not numero_pedido:
        return {"status": "erro", "mensagem": "Número do pedido ausente."}

    access_token = ""
    if db_connection:
        if token_record := await db_connection.fetchrow(
            "SELECT access_token FROM picpay_tokens ORDER BY id DESC LIMIT 1"
        ):
            access_token = token_record["access_token"]

    if not access_token:
        return {"status": "erro", "mensagem": "Token do PicPay ausente."}

    carrinho_json = payload_fila.get("carrinho_json", [])
    try:
        carrinho_json = (
            json.loads(carrinho_json)
            if isinstance(carrinho_json, str)
            else carrinho_json
        )
    except Exception:
        carrinho_json = []

    carrinho_em_linha = formatar_carrinho_em_linha(carrinho_json)
    valor_total = float(payload_fila.get("valor_total", 0))

    url_picpay = "https://api.picpay.com/v1/paymentlink/create"
    exp_date = (datetime.now(timezone.utc) + timedelta(minutes=30)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    order_number_ext = (
        f"{numero_pedido}{jid[10:] if jid and len(jid) > 10 else str(jid or '')}"
    )

    payload_picpay = {
        "charge": {
            "name": f"Pedido: TLF-{numero_pedido}",
            "description": carrinho_em_linha,
            "order_number": order_number_ext,
            "redirect_url": "https://wa.me/5511958987801",
            "payment": {
                "methods": ["BRCODE", "CREDIT_CARD"],
                "brcode_arrangements": ["PIX"],
            },
            "amounts": {"product": int(round(valor_total * 100))},
        },
        "options": {
            "allow_create_pix_key": True,
            "card_max_installment_number": 1,
            "expired_at": exp_date,
        },
    }

    headers_picpay = {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token.replace('Bearer ', '').strip()}",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url_picpay, json=payload_picpay, headers=headers_picpay, timeout=60.0
        )

    if response.status_code not in [200, 201]:
        return {"status": "erro", "mensagem": response.text}

    dados_cobranca = response.json()
    link_pagamento = dados_cobranca.get("link", "")
    id_pagamento = (
        link_pagamento.split("/")[4]
        if "/" in link_pagamento and len(link_pagamento.split("/")) > 4
        else ""
    )
    reference_payment = dados_cobranca.get("details", {}).get(
        "orderNumber", order_number_ext
    )

    payload_wa = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": telefone_real,
        "type": "text",
        "text": {
            "preview_url": True,
            "body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\nFaça o pagamento do \nseu pedido *(TLF-{numero_pedido})*\nclicando no link abaixo:\n\n{link_pagamento}",
        },
    }

    sql_update_pedido = f"UPDATE pedidos SET id_pagamento = '{id_pagamento}', status_pagamento = 'link_criado', status_pedido = 'PAGAMENTO_PENDENTE', reference_payment = '{reference_payment}', data_criacao = NOW() WHERE numero_pedido = '{numero_pedido}';"
    sql_update_conversas = f"UPDATE conversas_bot SET estado_conversa = 'aguardando_pagamento', telefone_real = '{telefone_real}', ultima_interacao = NOW() WHERE telefone_real = '{telefone_real}';"

    return {
        "sql_update": [sql_update_pedido, sql_update_conversas],
        "payload": payload_wa,
    }
