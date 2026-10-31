import logging

# 1. IMPORTA O NOVO SUBFLUXO DE AJUDA
from subfluxos.ajuda_e_atendimento import processar_ajuda_pedido

logger = logging.getLogger(__name__)


async def processar_menu_inicio(
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
        sql_update = f"UPDATE conversas_bot SET estado_conversa = 'menu_alternativo', expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{user_id}';"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n*_{primeiro_nome}_*,\nEntre em contato conosco:\n\n📲 → Redes Sociais: @thelordtrufas\n\n_*Assuntos gerais:*_\n📧 → contato@thelordtrufas.shop\n\n_*Nossa marca em seu evento:*_\n📧 → eventos@thelordtrufas.shop\n\n_*Parceria com marcas ou influencers:*_\n📧 → parcerias@thelordtrufas.shop\n\n_*Reclamações e Sugestões:*_\n📧 → sac@thelordtrufas.shop\n"
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
        }
        return {"sql_update": sql_update, "payload": payload}

    elif opcao == "3":
        # 2. DELEGA TODA A LÓGICA DE TRANSFERÊNCIA PARA O SUBFLUXO ESPECIALIZADO
        return await processar_ajuda_pedido(
            user_id, telefone_real, primeiro_nome, cliente_db
        )

    return {
        "sql_update": None,
        "payload": {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real,
            "type": "text",
            "text": {
                "body": "Opção inválida. Por favor, escolha uma das opções disponíveis no menu."
            },
        },
    }
