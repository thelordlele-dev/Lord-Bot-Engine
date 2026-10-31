from datetime import datetime, timezone
import logging
import secrets
import httpx
import os

logger = logging.getLogger(__name__)


async def processar_envio_avaliacao(
    db_connection=None, whatsapp_config: dict = None
) -> dict:
    sql_busca_pedidos = "SELECT jid, primeiro_nome, numero_pedido, telefone_real FROM pedidos WHERE status_pedido = 'AVALIACAO' AND data_criacao < NOW() - INTERVAL '1 hours' AND data_criacao > NOW() - INTERVAL '12 hours';"

    pedidos = []
    if db_connection:
        pedidos = await db_connection.fetch(sql_busca_pedidos)
    if not pedidos:
        return {"status": "sucesso", "pedidos_enviados": 0}

    resultados_envio = []

    async with httpx.AsyncClient() as client:
        for pedido in pedidos:
            jid, primeiro_nome, numero_pedido, telefone_real = (
                pedido["jid"],
                pedido.get("primeiro_nome", "Cliente"),
                pedido["numero_pedido"],
                pedido["telefone_real"],
            )
            destinatario = telefone_real if telefone_real else jid
            if not destinatario or not numero_pedido:
                continue

            flow_token = secrets.token_hex(16)
            url_whatsapp = f"https://graph.facebook.com/v26.0/{whatsapp_config.get('WHATSAPP_PHONE_NUMBER_ID')}/messages"
            payload_whatsapp = {
                "messaging_product": "whatsapp",
                "to": destinatario,
                "recipient_type": "individual",
                "type": "interactive",
                "interactive": {
                    "type": "flow",
                    "body": {
                        "text": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_*{primeiro_nome}*_,\n\n*Avalie* o seu pedido *TLF-{numero_pedido}* e nos ajude a melhorar! 😉\n\n_Basta clicar no botão abaixo:_\n"
                    },
                    "action": {
                        "name": "flow",
                        "parameters": {
                            "flow_message_version": "3",
                            "flow_token": flow_token,
                            "flow_id": "818430230857559",
                            "flow_cta": "Avaliar Pedido",
                        },
                    },
                },
            }
            headers = {
                "Authorization": f"Bearer {whatsapp_config.get('token')}",
                "Content-Type": "application/json",
            }

            sucesso_envio = False
            if whatsapp_config:
                response = await client.post(
                    url_whatsapp, json=payload_whatsapp, headers=headers, timeout=30.0
                )
                if response.status_code in [200, 201]:
                    sucesso_envio = True

            if sucesso_envio and db_connection:
                await db_connection.execute(
                    "UPDATE pedidos SET status_pedido = 'AVALIANDO' WHERE numero_pedido = $1 AND jid = $2;",
                    numero_pedido,
                    jid,
                )
                resultados_envio.append(
                    {"numero_pedido": numero_pedido, "status": "enviado"}
                )

    return {
        "status": "sucesso",
        "pedidos_enviados": len(resultados_envio),
        "detalhes": resultados_envio,
    }
