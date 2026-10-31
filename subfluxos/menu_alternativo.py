import logging
from subfluxos.gerenciador_encerramento import processar_encerramento_sessao

logger = logging.getLogger(__name__)


async def processar_menu_alternativo(
    user_id: str,
    telefone_real: str,
    primeiro_nome: str,
    opcao_escolhida: str,
    cliente_db: dict,
) -> dict:
    opcao = str(opcao_escolhida).strip()

    if opcao == "1":
        sql_update = f"UPDATE conversas_bot SET estado_conversa = 'aguardando_categoria', expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{user_id}';"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n*_{primeiro_nome}_*,\nqual cardápio você gostaria de ver hoje? 🤔\n"
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": "1", "title": "🍫 Individuais"},
                        },
                        {"type": "reply", "reply": {"id": "2", "title": "📦 Combos"}},
                        {
                            "type": "reply",
                            "reply": {"id": "3", "title": "⏮️ Menu Principal"},
                        },
                    ]
                },
            },
        }
        return {"sql_update": sql_update, "payload": payload}

    elif opcao == "2":
        sql_update = f"UPDATE conversas_bot SET estado_conversa = 'menu_inicio', expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{user_id}';"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n*_{primeiro_nome}_*,\naqui está o *Menu Principal* novamente.\n"
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": "1", "title": "📝 Fazer pedido"},
                        },
                        {
                            "type": "reply",
                            "reply": {"id": "2", "title": "📱 | 📢 Redes/Contatos"},
                        },
                        {"type": "reply", "reply": {"id": "3", "title": "🆘 Ajuda"}},
                    ]
                },
            },
        }
        return {"sql_update": sql_update, "payload": payload}

    elif opcao == "3":
        carrinho = cliente_db.get("carrinho_json", "[]")
        return await processar_encerramento_sessao(
            user_id, telefone_real, primeiro_nome, carrinho, "sair"
        )

    return {
        "sql_update": None,
        "payload": {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n*_{primeiro_nome}_*,\nsua mensagem não é válida. Por favor escolha uma das opções abaixo:\n"
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": "2", "title": "⏮️ Menu Principal"},
                        },
                        {"type": "reply", "reply": {"id": "3", "title": "❌ Sair"}},
                    ]
                },
            },
        },
    }
