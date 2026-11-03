import uuid
from subfluxos.loja import obter_status_atual_loja


async def gerar_mensagem_boas_vindas(jid, telefone_real):
    # 1. VERIFICA O STATUS DA LOJA PRIMEIRO
    status_loja = await obter_status_atual_loja()

    # 2. SE ESTIVER FECHADA, BARRA O CLIENTE AQUI!
    if not status_loja["aberta"]:
        motivo = status_loja.get("motivo", "Fechada.")
        payload_fechado = {
            "messaging_product": "whatsapp",
            "to": telefone_real,
            "recipient_type": "individual",
            "type": "text",
            "text": {
                "body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\nOlá, infelizmente não podemos seguir com o seu atendimento agora.\n\n{motivo}"
            },
        }
        # Retorna o status 'ignorar_mensagem' para a máquina de estados não avançar o cliente
        sql_manter = f"UPDATE conversas_bot SET estado_conversa = 'primeiro_contato' WHERE jid = '{jid}';"
        return {"sql_update": sql_manter, "payload": payload_fechado}

    # 3. SE ESTIVER ABERTA, SEGUE O FLUXO NORMAL
    flow_token = uuid.uuid4().hex

    sql_insercao = f"""
        INSERT INTO conversas_bot (jid, telefone_real, estado_conversa, carrinho_json, mapa_id_json) 
        VALUES ('{jid}', '{telefone_real}', 'primeiro_contato', '[]', '{{}}') 
        ON CONFLICT (jid) DO NOTHING;
    """

    payload = {
        "messaging_product": "whatsapp",
        "to": telefone_real,
        "recipient_type": "individual",
        "type": "interactive",
        "interactive": {
            "type": "flow",
            "body": {
                "text": "_*Oii, tudo Bem? Seja Bem-Vindo(a)*_\n\nMuito Prazer,\neu sou a _*Kakaw 👸🏾*_,\na assistente virtual\nda _*TheLordTrufas 🍫✨.*_\n\nCadastre seu *Nome* para\nseguir com o atendimento\nclicando no botão abaixo:\n"
            },
            "action": {
                "name": "flow",
                "parameters": {
                    "flow_message_version": "3",
                    "flow_token": flow_token,
                    "flow_id": "1490206002178974",
                    "flow_cta": "Cadastrar Nome",
                },
            },
        },
    }

    return {"sql_update": sql_insercao, "payload": payload}
