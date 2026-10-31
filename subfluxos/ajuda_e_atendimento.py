import uuid
import os
import httpx
import logging

logger = logging.getLogger(__name__)

# Configurações do Chatwoot
CHATWOOT_URL = os.getenv("CHATWOOT_API_URL")
CHATWOOT_ACCOUNT_ID = os.getenv("CHATWOOT_ACCOUNT_ID", "1")
CHATWOOT_TOKEN = os.getenv("CHATWOOT_ACCESS_TOKEN", "")


async def _integrar_chatwoot_ajuda(
    telefone_real: str, primeiro_nome: str, carrinho: str, jid: str
):
    if not CHATWOOT_TOKEN:
        print("❌ Chatwoot token não configurado (.env CHATWOOT_ACCESS_TOKEN)")
        return

    headers = {"api_access_token": CHATWOOT_TOKEN, "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        try:
            # 1. Buscar todas as Conversas em Aberto primeiro (Exatamente como no n8n)
            url_convs = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/conversations?status=open"
            resp_convs = await client.get(url_convs, headers=headers)

            if resp_convs.status_code != 200:
                print(f"Erro ao buscar conversas no Chatwoot: {resp_convs.text}")
                return

            # O payload do Chatwoot geralmente vem dentro de "data" -> "payload" ou direto em "payload"
            dados_json = resp_convs.json()
            conversas = dados_json.get("data", {}).get("payload", [])
            if not conversas and "payload" in dados_json:
                conversas = dados_json.get("payload", [])

            # 2. Roteador de Filtro (Igual ao nó Filter1 do n8n)
            conversation_id = None
            telefone_limpo = str(telefone_real).replace("+", "").strip()
            jid_limpo = str(jid).replace("+", "").strip()

            for conv in conversas:
                # Meta.sender.phone_number
                sender_phone = (
                    conv.get("meta", {}).get("sender", {}).get("phone_number") or ""
                )
                sender_phone_limpo = str(sender_phone).replace("+", "").strip()

                # Messages[0].conversation.contact_inbox.source_id
                source_id = ""
                mensagens = conv.get("messages", [])
                if mensagens and isinstance(mensagens, list):
                    source_id = (
                        mensagens[0]
                        .get("conversation", {})
                        .get("contact_inbox", {})
                        .get("source_id")
                        or ""
                    )
                source_id_limpo = str(source_id).replace("+", "").strip()

                # Condições do nó Filter1 do n8n (Verifica telefone_real ou jid)
                if telefone_limpo and (
                    telefone_limpo == sender_phone_limpo
                    or telefone_limpo == source_id_limpo
                ):
                    conversation_id = conv.get("id")
                    break
                if jid_limpo and (
                    jid_limpo == sender_phone_limpo or jid_limpo == source_id_limpo
                ):
                    conversation_id = conv.get("id")
                    break

            if not conversation_id:
                print(
                    f"⚠️ Nenhuma conversa aberta encontrada no Chatwoot para o número {telefone_limpo}."
                )
                return

            # 3. Atribuir Conversa ao Agente (ID 1)
            url_assign = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/conversations/{conversation_id}/assignments"
            await client.post(url_assign, headers=headers, json={"assignee_id": 1})

            # 4. Criar a Etiqueta 'ajuda_pedido'
            url_labels = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/conversations/{conversation_id}/labels"
            await client.post(
                url_labels, headers=headers, json={"labels": ["ajuda_pedido"]}
            )

            # 5. Criar a Mensagem Privada
            url_msg = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/conversations/{conversation_id}/messages"
            carrinho_formatado = carrinho if carrinho and carrinho != "[]" else "Vazio"
            nota_privada = f"⚠️ *ATENDIMENTO SOLICITADO VIA BOT* ⚠️\n\n*Cliente:* {primeiro_nome}\n*Carrinho Atual:* {carrinho_formatado}\n\n_O bot foi pausado. Assuma o atendimento._"

            payload_msg = {
                "content": nota_privada,
                "message_type": "outgoing",
                "private": True,
                "content_type": "text",
            }
            await client.post(url_msg, headers=headers, json=payload_msg)

            print(
                f"✅ Integração com Chatwoot realizada com sucesso! Conversa ID: {conversation_id}"
            )

        except Exception as e:
            print(f"❌ Erro na integração com Chatwoot: {e}")


async def processar_ajuda_pedido(
    user_id: str, telefone_real: str, primeiro_nome: str, dados_estado: dict
) -> dict:
    """
    [MÓDULO] - Ajuda e Atendimento
    Acionado quando o cliente clica em "Ajuda" no menu.
    """
    carrinho = dados_estado.get("carrinho_json", "[]")

    # 1. Dispara integração do Chatwoot (Agora passando o user_id para o filtro)
    await _integrar_chatwoot_ajuda(telefone_real, primeiro_nome, carrinho, user_id)

    # 2. Atualiza banco de dados para pausar o bot
    sql_update = f"UPDATE conversas_bot SET estado_conversa = 'ajuda_pedido', is_bot_paused = TRUE WHERE jid = '{user_id}';"

    # 3. Payload de resposta para o WhatsApp (INTACTO conforme as suas instruções)
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "type": "text",
        "text": {
            "body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_*{primeiro_nome}*_,\nnão se preocupe, já estou\nte transferindo para que\num *atendente humano* te ajude\nda melhor forma possível!🙋‍♀️\n\nAguarde...⏳\n"
        },
    }

    return {"sql_update": sql_update, "payload": payload}


async def processar_retorno_pos_ajuda(
    user_id: str, telefone_real: str, primeiro_nome: str, dados_estado: dict
) -> dict:
    """
    [MÓDULO 15.3 - RETORNO BOT AJUDA]
    Retorna o cliente para o bot após o atendimento humano,
    limpa os dados da sessão e envia o flow de avaliação.
    """
    flow_token = str(uuid.uuid4())

    sql_update = f"""
        UPDATE conversas_bot 
        SET estado_conversa = 'cliente_existe', 
            carrinho_json = '[]'::jsonb, 
            mapa_id_json = '{{}}'::jsonb, 
            print_carrinho = NULL, 
            pagina_atual = 1, 
            categoria_selecionada = NULL, 
            is_bot_paused = FALSE, 
            expirando = FALSE, 
            valor_pedido = NULL,
            ultima_interacao = NOW() 
        WHERE jid = '{user_id}';
    """

    payload = {
        "messaging_product": "whatsapp",
        "to": telefone_real or user_id,
        "recipient_type": "individual",
        "type": "interactive",
        "interactive": {
            "type": "flow",
            "body": {
                "text": (
                    f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n"
                    f"_*{primeiro_nome}*_,\n"
                    f"avalie o nosso atendimento, clicando no botão abaixo:\n\n"
                    f"*📢 Sua avaliação é extremamente importante para que a TheLordTrufas evolua e melhore todos os dias.*\n"
                )
            },
            "action": {
                "name": "flow",
                "parameters": {
                    "flow_message_version": "3",
                    "flow_token": flow_token,
                    "flow_id": "1732007060816107",
                    "flow_cta": "Avaliar Atendimento",
                },
            },
        },
    }

    return {"sql_update": sql_update, "payload": payload}
