import logging
import os
import httpx
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Alterado para buscar do ambiente de forma segura
NOTION_TOKEN = os.getenv("NOTION_API_KEY", "")
HEADERS_NOTION = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}
DATABASE_ID_AVALIACAO_ATENDIMENTO = os.getenv("DATABASE_ID_AVALIACAO_ATENDIMENTO", "")


async def criar_avaliacao_atendimento_notion(
    nome_cliente: str,
    whatsapp_num: str,
    resolveu: bool,
    coracoes: str,
    data_atendimento: str,
    comentario: str,
):
    if not NOTION_TOKEN:
        print(
            "❌ Token do Notion ausente. Verifique se o NOTION_API_KEY está no seu ficheiro .env"
        )
        return

    wa_number_clean = (
        float(str(whatsapp_num).replace("+", ""))
        if str(whatsapp_num).replace("+", "").replace(".", "").isdigit()
        else 0.0
    )

    properties = {
        "Cliente": {"title": [{"text": {"content": nome_cliente}}]},
        "WhatsApp": {"rich_text": [{"text": {"content": str(whatsapp_num)}}]},
        "Resolvida": {"checkbox": resolveu},
        "Avaliação": {"select": {"name": coracoes}},
        "Data Atendimento": {"date": {"start": data_atendimento}},
    }

    payload = {
        "parent": {"database_id": DATABASE_ID_AVALIACAO_ATENDIMENTO},
        "properties": properties,
    }

    if comentario:
        payload["children"] = [
            {
                "object": "block",
                "heading_2": {"rich_text": [{"text": {"content": comentario}}]},
            }
        ]

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://api.notion.com/v1/pages", headers=HEADERS_NOTION, json=payload
            )

            if response.status_code in [200, 201]:
                print(
                    f"✅ Avaliação salva com sucesso no Notion para o cliente {nome_cliente}!"
                )
            else:
                # Se o Notion recusar, o erro exato aparecerá aqui
                print(f"❌ Erro ao salvar no Notion. Status: {response.status_code}")
                print(f"❌ Detalhes do Erro Notion: {response.text}")

        except Exception as e:
            print(f"❌ Falha de comunicação com a API do Notion: {e}")


async def processar_cadastro_avaliacao_atendimento(
    payload_flow: dict, db_connection=None
) -> dict:
    resolveu_str = payload_flow.get("screen_0_Escolha_a_opo_0", "Sim").strip()
    nota = str(payload_flow.get("screen_0_Escolha_a_opo_1", "5")).strip()
    comentario = payload_flow.get("screen_0_comentrio_2", "").strip()
    data_atendimento = payload_flow.get(
        "data_atendimento", datetime.now(timezone.utc).isoformat()
    )
    jid = payload_flow.get("Jid")

    if not jid:
        return {"status": "erro", "mensagem": "JID do cliente ausente."}

    # Busca os dados do cliente
    sql_busca = "SELECT jid, nome_cliente, primeiro_nome, telefone_real FROM conversas_bot WHERE jid = $1 LIMIT 1;"

    cliente_info = None
    if db_connection:
        cliente_info = await db_connection.fetchrow(sql_busca, jid)

    nome_cliente = (
        cliente_info["nome_cliente"]
        if cliente_info and cliente_info.get("nome_cliente")
        else "Cliente"
    )
    telefone_real = (
        cliente_info["telefone_real"]
        if cliente_info and cliente_info.get("telefone_real")
        else jid
    )

    mapa_coracoes = {
        "1": "🩵",
        "2": "🩵🩵",
        "3": "🩵🩵🩵",
        "4": "🩵🩵🩵🩵",
        "5": "🩵🩵🩵🩵🩵",
    }
    coracoes_formatados = mapa_coracoes.get(nota, "🩵🩵🩵🩵🩵")
    foi_resolvida = resolveu_str.lower() == "sim"

    print(f"⏳ A tentar gravar a avaliação do cliente {nome_cliente} no Notion...")
    await criar_avaliacao_atendimento_notion(
        nome_cliente,
        telefone_real,
        foi_resolvida,
        coracoes_formatados,
        data_atendimento,
        comentario,
    )
