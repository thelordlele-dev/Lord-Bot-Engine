import uuid


async def gerar_mensagem_boas_vindas(jid, telefone_real):
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
