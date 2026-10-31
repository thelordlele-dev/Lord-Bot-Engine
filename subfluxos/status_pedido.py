from datetime import datetime, timezone
import logging
import httpx
import os

logger = logging.getLogger(__name__)
CHATWOOT_BASE_URL = os.getenv("CHATWOOT_API_URL")


async def processar_status_pagamento(
    payload_gateway: dict,
    pedido_db: dict,
    db_connection=None,
    chatwoot_config: dict = None,
) -> dict:
    external_reference = payload_gateway.get("external_reference")
    status_gateway = payload_gateway.get("status")

    if not external_reference:
        return {"mensagem": "External reference não encontrada."}

    jid_cliente, numero_pedido_fmt, f_pagamento, p_nome = (
        pedido_db.get("jid"),
        f"TLF-{pedido_db.get('numero_pedido')}",
        pedido_db.get("forma_pagamento", "PIX"),
        pedido_db.get("primeiro_nome", "Cliente"),
    )

    if status_gateway == "PAYED":
        if db_connection:
            await db_connection.execute(
                "UPDATE pedidos SET status_pagamento = 'pagamento_efetuado', status_pedido = 'PAGAMENTO_APROVADO' WHERE reference_payment = $1;",
                external_reference,
            )
        return {
            "resultado": "pagamento_aprovado",
            "chatwoot": {
                "acao": "aprovar",
                "jid": jid_cliente,
                "numero_pedido": numero_pedido_fmt,
                "forma_pagamento": f_pagamento,
            },
        }

    elif status_gateway == "CANCELLED":
        status_db = (
            f"CANCELADO_{payload_gateway.get('status_detail', 'CANCELADO').upper()}"
        )
        if db_connection:
            await db_connection.execute(
                "UPDATE pedidos SET status_pagamento = 'pagamento_cancelado', status_pedido = $1 WHERE reference_payment = $2;",
                status_db,
                external_reference,
            )
            await db_connection.execute(
                "UPDATE conversas_bot SET estado_conversa = 'cliente_existe', expirando = FALSE, carrinho_json = '[]'::jsonb, mapa_id_json = '{}'::jsonb, pagina_atual = 1, categoria_selecionada = NULL, ultima_interacao = NOW() WHERE jid = $1;",
                jid_cliente,
            )
        return {
            "resultado": "pagamento_cancelado",
            "chatwoot": {"acao": "cancelar", "jid": jid_cliente},
            "payload_whatsapp": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": jid_cliente,
                "type": "text",
                "text": {
                    "body": f"_*{p_nome}*_,\n\nSeu pedido foi *CANCELADO*\npor falta de pagamento. ❌\n\nObrigado pela visita!\nEsperamos que volte logo para saborear nossas deliciosas Trufas de Colher 🤎"
                },
            },
        }

    return {"mensagem": f"Status não mapeado: {status_gateway}"}


async def executar_integracao_chatwoot(
    conversation_id: str, acao: str, detalhes: dict, config: dict
):
    if not config or not conversation_id:
        return
    base_url, headers = config.get(
        "base_url", "https://chatwoot.thelordbot.online/api/v1/accounts/1"
    ), {
        "Authorization": f"Bearer {config.get('token')}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        if acao == "aprovar":
            await client.post(
                f"{base_url}/conversations/{conversation_id}/labels",
                json={"labels": ["enviar_pedido"]},
                headers=headers,
            )
            await client.post(
                f"{base_url}/conversations/{conversation_id}/messages",
                json={
                    "content": f"*✅ PAGAMENTO APROVADO ✅* \n\n*📃 PEDIDO: {detalhes.get('numero_pedido')}*\n\n*💳 F. PAGAMENTO: {detalhes.get('forma_pagamento')}*",
                    "message_type": "outgoing",
                    "private": True,
                    "content_type": "text",
                },
                headers=headers,
            )
        elif acao == "cancelar":
            await client.post(
                f"{base_url}/conversations/{conversation_id}/labels",
                json={"labels": ["pedido_cancelado"]},
                headers=headers,
            )
            await client.post(
                f"{base_url}/conversations/{conversation_id}/messages",
                json={
                    "content": "*❌ PAGAMENTO CANCELADO ❌*",
                    "message_type": "outgoing",
                    "private": True,
                    "content_type": "text",
                },
                headers=headers,
            )
