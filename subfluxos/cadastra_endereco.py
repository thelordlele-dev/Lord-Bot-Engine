import logging
import os
import httpx

logger = logging.getLogger(__name__)

NOTION_API_URL = "https://api.notion.com/v1"
DATABASE_ID_CLIENTES = os.getenv("DATABASE_ID_CLIENTES")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")


async def processar_cadastro_endereco(
    dados_formulario: dict,
    user_id: str,
    telefone_real: str,
    db_connection,
    notion_headers: dict,
    whatsapp_api_config: dict,
) -> dict:
    rua = dados_formulario.get("screen_0_Endereo_0", "").strip().upper()
    numero = dados_formulario.get("screen_0_Nmero_1", "").strip()
    bairro = dados_formulario.get("screen_0_Bairro_2", "").strip().upper()
    cep_raw = dados_formulario.get("screen_0_CEP_3", "").strip()
    complemento = dados_formulario.get("screen_0_Complemento_4", "").strip().upper()

    cep_formatado = f"{cep_raw[:5]}-{cep_raw[5:]}" if len(cep_raw) >= 8 else cep_raw
    endereco_completo = f"{rua}, {numero}"

    await _atualizar_notion_cliente(
        telefone_real or user_id,
        endereco_completo,
        bairro,
        complemento,
        cep_formatado,
        notion_headers,
    )

    # (Mantenha o código inicial da função igual)

    # 1. Envia para o Worker fazer o UPDATE
    sql_update = f"""
        UPDATE conversas_bot 
        SET estado_conversa = 'finalizando_pedido', 
            endereco = '{endereco_completo}', 
            bairro = '{bairro}', 
            complemento = '{complemento}', 
            CEP = '{cep_raw}', 
            expirando = FALSE, 
            ultima_interacao = NOW() 
        WHERE jid = '{user_id}';
    """

    texto_resumo = f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n*📍→ RUA/Nº:*\n\n{endereco_completo}\n\n*📍→ BAIRRO:*\n\n{bairro}\n\n*📍→ CEP:*\n\n{cep_formatado}\n\n"
    texto_resumo += f"*📍→ COMPLEMENTO:*\n\n{complemento}\n\n" if complemento else ""

    # 2. Envia para o Worker disparar a mensagem
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": telefone_real if telefone_real else user_id,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": f"{texto_resumo}Os dados do *endereço* acima estão corretos?"
            },
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "1", "title": "📍✅ Correto"}},
                    {"type": "reply", "reply": {"id": "2", "title": "📍❌ Errado"}},
                ]
            },
        },
    }

    # Retorna o dicionário no formato que o Worker ama!
    return {"sql_update": sql_update, "payload": payload}


async def _atualizar_notion_cliente(
    telefone: str,
    endereco: str,
    bairro: str,
    complemento: str,
    cep: str,
    notion_headers: dict,
):
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{NOTION_API_URL}/databases/{DATABASE_ID_CLIENTES}/query",
                json={
                    "filter": {
                        "property": "Whatsapp",
                        "rich_text": {"equals": str(telefone)},
                    }
                },
                headers=notion_headers,
            )
            results = resp.json().get("results", [])
            if results:
                page_id = results[0]["id"]
                properties = {
                    "Endereço": {
                        "rich_text": [{"text": {"content": endereco}}]
                    },
                    "Bairro": {"rich_text": [{"text": {"content": bairro}}]},
                    "Complemento": {
                        "rich_text": [{"text": {"content": complemento or ""}}]
                    },
                    "CEP": {"rich_text": [{"text": {"content": cep}}]},
                }
                await client.patch(
                    f"{NOTION_API_URL}/pages/{page_id}",
                    json={"properties": properties},
                    headers=notion_headers,
                )
    except Exception as e:
        logger.error("Erro Notion: %s", e)


async def _enviar_whatsapp_payload(destinatario: str, payload: dict, config: dict):
    url = f"https://graph.facebook.com/v26.0/{config.get('WHATSAPP_PHONE_NUMBER_ID')}/messages"
    headers = {
        "Authorization": f"Bearer {config.get('token')}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload, headers=headers)
