import logging

logger = logging.getLogger(__name__)


async def processar_retorno_menu(
    user_id: str, telefone_real: str, cliente_db: dict
) -> dict:
    sql_update = f"UPDATE conversas_bot SET estado_conversa = 'menu_inicio', expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{user_id}';"

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": telefone_real,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": "_*👸🏾 Kakaw - TheLordTrufas.*_\n\nAqui está o *Menu Principal* novamente.\n"
            },
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "1", "title": "📝 Fazer pedido"}},
                    {"type": "reply", "reply": {"id": "2", "title": "📱 | 📢 Redes/Contatos"}},
                    {"type": "reply", "reply": {"id": "3", "title": "🆘 Ajuda"}},
                ]
            },
        },
    }

    return {"sql_update": sql_update, "payload": payload}
