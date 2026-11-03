import logging
from subfluxos.loja import obter_status_atual_loja

logger = logging.getLogger(__name__)

# Altere para True quando a promoção estiver ativa e False quando acabar
PROMO_LEVE_3_PAGUE_2 = False


async def executar_fluxo_cliente_existe(jid: str, primeiro_nome: str) -> dict:
    logger.info("Processando fluxo de cliente existente para JID: %s", jid)

    # 1. VERIFICA O STATUS DA LOJA PRIMEIRO
    status_loja = await obter_status_atual_loja()

    # 2. SE ESTIVER FECHADA, BARRA O CLIENTE AQUI!
    if not status_loja["aberta"]:
        motivo = status_loja.get("motivo", "Fechada.")
        payload_fechado = {
            "type": "text",
            "text": {
                "body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\nOlá _*{primeiro_nome}*_, infelizmente não podemos seguir com o seu atendimento agora.\n\n{motivo}"
            },
        }

        # Mantém o cliente no mesmo estado para que ele possa tentar de novo mais tarde
        sql_manter = f"UPDATE conversas_bot SET estado_conversa = 'cliente_existe', ultima_interacao = NOW() WHERE jid = '{jid}';"
        return {"sql_update": sql_manter, "mensagens_multiplas": [payload_fechado]}

    # 3. SE ESTIVER ABERTA, SEGUE O FLUXO NORMAL
    acoes = []

    if PROMO_LEVE_3_PAGUE_2:
        texto_aviso = (
            "_*🚨 ATENÇÃO 🚨*_\n\n"
            "A promoção *(LEVE 3 E PAGUE 2)* só será desbloqueada se não houver "
            "sabores repetidos dentro dos 3 itens escolhidos. O *DESCONTO* será "
            "aplicado antes da criação do *link de pagamento*."
        )
        acoes.append(
            {
                "type": "text",
                "text": {"body": texto_aviso},
            }
        )

    # Payload do Menu Principal Interativo
    payload_menu = {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_*{primeiro_nome}*_,\nque bom ter você de volta!\nVamos continuar com o seu atendimento. 😁\n"
            },
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "1", "title": "📝 Fazer pedido"}},
                    {
                        "type": "reply",
                        "reply": {"id": "2", "title": "📱 | 📢 Redes/Contatos"},
                    },
                    {"type": "reply", "reply": {"id": "3", "title": "🆘 Ajuda"}},
                ]
            },
        },
    }
    acoes.append(payload_menu)

    sql_update = f"""
        UPDATE conversas_bot 
        SET estado_conversa = 'menu_inicio', 
            expirando = FALSE, 
            ultima_interacao = NOW() 
        WHERE jid = '{jid}';
    """

    return {"sql_update": sql_update, "mensagens_multiplas": acoes}
