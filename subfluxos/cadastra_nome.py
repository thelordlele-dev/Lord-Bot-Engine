import json
import logging
import httpx

logger = logging.getLogger(__name__)

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_DATABASE_CLIENTES_ID = "09ecc826e430417cbca704761420979b"


async def processar_cadastro_nome(
    dados_formulario: dict,
    user_id: str,
    telefone_real: str,
    db_connection,
    notion_headers: dict,
    whatsapp_api_config: dict,
) -> dict:
    nome_social = (
        dados_formulario.get("screen_0_Nome_Nome_Social_0", "").strip().upper()
    )
    sobrenome = dados_formulario.get("screen_0_Sobrenome_1", "").strip().upper()

    primeiro_nome = nome_social
    nome_cliente = f"{nome_social} {sobrenome}".strip()

    logger.info(f"Cadastrando cliente | JID: {user_id} | Nome: {nome_cliente}")

    sql_update = f"""
        UPDATE conversas_bot 
        SET nome_cliente = '{nome_cliente}',
            primeiro_nome = '{primeiro_nome}',
            estado_conversa = 'menu_inicio'
        WHERE jid = '{user_id}';
    """

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": telefone_real if telefone_real else user_id,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n*{primeiro_nome}* escolha uma das\nopções no *MENU* disponíveis abaixo:\n"
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

    genero_estimado = _estimar_genero(primeiro_nome)
    try:
        # CORREÇÃO: Enviando os 5 argumentos na ordem correta, incluindo o user_id.
        await _criar_pagina_notion(
            nome_cliente,
            telefone_real or user_id,
            genero_estimado,
            user_id,
            notion_headers,
        )
    except Exception as e:
        logger.error(f"Erro ao salvar no Notion: {e}")

    return {"sql_update": sql_update, "payload": payload}


async def _criar_pagina_notion(
    nome_cliente: str, telefone: str, genero: str, user_id: str, notion_headers: dict
):
    payload = {
        "parent": {"database_id": NOTION_DATABASE_CLIENTES_ID},
        "properties": {
            "Nome": {"title": [{"text": {"content": nome_cliente}}]},
            "Whatsapp": {"rich_text": [{"text": {"content": str(telefone)}}]},
            "CRM": {"status": {"name": "Interesse"}},
            "Genêro": {"select": {"name": genero}},
            "user_id": {"rich_text": [{"text": {"content": str(user_id)}}]},
        },
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{NOTION_API_URL}/pages", json=payload, headers=notion_headers
        )

        print(f">>> [NOTION] Tentativa de cadastro. Status: {response.status_code}")

        if response.status_code != 200:
            print(f">>> [NOTION] ERRO DETALHADO: {response.text}")


def _estimar_genero(primeiro_nome: str) -> str:
    nome = primeiro_nome.strip().split()[0].lower()
    if nome.endswith("a") or nome.endswith("z"):
        return "Feminino"
    return "Masculino"
