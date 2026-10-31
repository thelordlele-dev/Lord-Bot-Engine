import os
import json
import aio_pika
import re
from fastapi import FastAPI, Request, HTTPException, Query, Response
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from config.database import conectar_db, desconectar_db

load_dotenv()
WEBHOOK_VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await conectar_db()
    yield
    await desconectar_db()


app = FastAPI(title="Kakaw Bot API", lifespan=lifespan)


@app.get("/webhook")
async def verificar_webhook(
    mode: str = Query(None, alias="hub.mode"),
    token: str = Query(None, alias="hub.verify_token"),
    challenge: str = Query(None, alias="hub.challenge"),
):
    if mode == "subscribe" and token == WEBHOOK_VERIFY_TOKEN:
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Token inválido")


@app.post("/webhook")
async def receber_webhook(request: Request):
    """Recebe o webhook da Meta e envia para a fila do RabbitMQ para processamento assíncrono."""
    dados = await request.json()

    try:
        entry = dados.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return {"status": "ok"}

        mensagem = messages[0]
        contacts = value.get("contacts", [])

        # 1. Extração do wa_id (telefone real) como base segura
        wa_id = mensagem.get("from")
        if contacts:
            wa_id = contacts[0].get("wa_id", wa_id)

        # 2. Busca do user_id (prioridade máxima solicitada)
        # Verifica se a Meta enviou o user_id no nível da mensagem, do value ou dos contatos
        user_id = mensagem.get("user_id") or value.get("user_id")
        if contacts and not user_id:
            user_id = contacts[0].get("user_id")

        # 3. Definição do JID oficial da conversa (user_id tem prioridade sobre wa_id)
        jid_identificador = str(user_id) if user_id else str(wa_id)

        primeiro_nome = (
            contacts[0].get("profile", {}).get("name", "Cliente").split()[0].upper()
            if contacts
            else "Cliente"
        )

        tipo_msg = mensagem.get("type")
        entrada_cliente = ""

        if tipo_msg == "text":
            entrada_cliente = mensagem.get("text", {}).get("body", "")
        elif tipo_msg == "interactive":
            interativo = mensagem.get("interactive", {})
            tipo_interativo = interativo.get("type")
            if tipo_interativo in ["button_reply", "list_reply"]:
                entrada_cliente = interativo.get(tipo_interativo, {}).get("id")
            elif tipo_interativo == "nfm_reply":
                nfm_data = interativo.get("nfm_reply", {})
                response_json_val = nfm_data.get("response_json", "{}")

                if isinstance(response_json_val, dict):
                    entrada_cliente = json.dumps(response_json_val)
                else:
                    entrada_cliente = response_json_val

        # Publica na fila do RabbitMQ com a nova estrutura de identificadores
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        async with connection:
            channel = await connection.channel()
            queue = await channel.declare_queue(
                "novos_pedidos", durable=True, arguments={"x-queue-type": "quorum"}
            )

            # Agora o Worker recebe o JID (prioridade user_id) E o telefone real separados!
            payload_fila = {
                "jid": jid_identificador,
                "telefone_real": wa_id,
                "primeiro_nome": primeiro_nome,
                "entrada_cliente": entrada_cliente,
            }

            await channel.default_exchange.publish(
                aio_pika.Message(body=json.dumps(payload_fila).encode()),
                routing_key="novos_pedidos",
            )

        return {"status": "success"}

    except Exception as e:
        print(f"Erro ao enfileirar mensagem do webhook: {e}")
        return {"status": "error"}


@app.post("/webhook/ajuda_finalizada")
async def webhook_ajuda_finalizada(request: Request):
    """
    Recebe o webhook do Chatwoot quando a etiqueta 'ajuda_finalizada' é inserida.
    """
    dados = await request.json()
    try:
        telefone = None
        # Tenta extrair o telefone de acordo com a estrutura do Chatwoot (source_id)
        if "messages" in dados and dados["messages"]:
            telefone = (
                dados["messages"][0]
                .get("conversation", {})
                .get("contact_inbox", {})
                .get("source_id")
            )

        if not telefone and "meta" in dados and "sender" in dados["meta"]:
            telefone = dados["meta"]["sender"].get("phone_number", "").replace("+", "")

        if telefone:
            telefone = telefone.strip()
            # Envia para a fila principal do Worker com um gatilho especial
            connection = await aio_pika.connect_robust(RABBITMQ_URL)
            async with connection:
                channel = await connection.channel()

                payload_fila = {
                    "jid": telefone,
                    "telefone_real": telefone,
                    "primeiro_nome": "Cliente",
                    "entrada_cliente": "/retorno_ajuda",  # Comando interno invisível
                }

                await channel.default_exchange.publish(
                    aio_pika.Message(body=json.dumps(payload_fila).encode()),
                    routing_key="novos_pedidos",
                )
                print(
                    f"✅ Webhook Chatwoot recebido. Cliente {telefone} a voltar para o Bot."
                )

    except Exception as e:
        print(f"Erro no webhook de ajuda finalizada: {e}")

    return {"status": "ok"}


@app.post("/webhook/criar_pagamento")
async def webhook_criar_pagamento(request: Request):
    """
    Recebe o webhook do Chatwoot quando o atendente envia o valor do frete e encerra/etiqueta.
    """
    dados = await request.json()
    try:
        telefone = None
        if "messages" in dados and dados["messages"]:
            telefone = (
                dados["messages"][0]
                .get("conversation", {})
                .get("contact_inbox", {})
                .get("source_id")
            )

        if not telefone and "meta" in dados and "sender" in dados["meta"]:
            telefone = dados["meta"]["sender"].get("phone_number", "").replace("+", "")

        if telefone:
            telefone = telefone.strip()
            # Envia para a fila do Worker com um gatilho secreto e embute o payload completo do Chatwoot
            connection = await aio_pika.connect_robust(RABBITMQ_URL)
            async with connection:
                channel = await connection.channel()

                payload_fila = {
                    "jid": telefone,
                    "telefone_real": telefone,
                    "primeiro_nome": "Cliente",
                    # Passamos os dados do webhook dentro do texto do cliente num formato JSON "disfarçado"
                    "entrada_cliente": f"/retorno_frete|||{json.dumps(dados)}",
                }

                await channel.default_exchange.publish(
                    aio_pika.Message(body=json.dumps(payload_fila).encode()),
                    routing_key="novos_pedidos",
                )
                print(f"✅ Webhook de Frete do Chatwoot recebido. Cliente {telefone}.")

    except Exception as e:
        print(f"Erro no webhook de retorna_pagamento: {e}")

    return {"status": "ok"}

@app.post("/webhook/pedido_finalizado")
async def webhook_pedido_finalizado(request: Request):
    """
    Recebe o webhook do Chatwoot quando o pedido é marcado com a etiqueta de finalizado.
    """
    dados = await request.json()
    try:
        telefone = None
        numero_pedido = ""
        
        if "messages" in dados and dados["messages"]:
            # Tenta pegar o telefone
            telefone = dados["messages"][0].get("conversation", {}).get("contact_inbox", {}).get("source_id")
            
            # Extrai o número do pedido do conteúdo da mensagem (como no n8n)
            conteudo_msg = dados["messages"][0].get("content", "")
            if match := re.search(r"PEDIDO:?\s*(\d+)", conteudo_msg, re.IGNORECASE):
                numero_pedido = match.group(1)
        
        if not telefone and "meta" in dados and "sender" in dados["meta"]:
            telefone = dados["meta"]["sender"].get("phone_number", "").replace("+", "")
            
        if telefone:
            telefone = telefone.strip()
            
            connection = await aio_pika.connect_robust(RABBITMQ_URL)
            async with connection:
                channel = await connection.channel()
                
                payload_fila = {
                    "jid": telefone, 
                    "telefone_real": telefone,
                    "primeiro_nome": "Cliente",
                    # Passamos o número do pedido extraído escondido no gatilho
                    "entrada_cliente": f"/pedido_finalizado|||{numero_pedido}"
                }
                
                await channel.default_exchange.publish(
                    aio_pika.Message(body=json.dumps(payload_fila).encode()),
                    routing_key="novos_pedidos"
                )
                print(f"✅ Webhook 'pedido_finalizado' do Chatwoot recebido. Cliente {telefone}.")
                
    except Exception as e:
        print(f"Erro no webhook de pedido_finalizado: {e}")
        
    return {"status": "ok"}
