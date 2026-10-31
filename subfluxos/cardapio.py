import json
import logging
import httpx
import os

logger = logging.getLogger(__name__)
NOTION_API_URL = "https://api.notion.com/v1"
NOTION_TOKEN = os.getenv("NOTION_API_KEY", "")


async def processar_busca_cardapio(
    user_id: str,
    telefone_real: str,
    primeiro_nome: str,
    tipo_selecionado: str,
    pagina_atual: int = 1,
    mapa_id_json: str = "{}",
    modo_cupom: bool = False,
    itens_ordenados_cache: str = None,
) -> dict:
    itens_por_pagina = 50 if tipo_selecionado == "Individuais" else 10
    itens_ordenados = []
    mapa_id = {}

    notion_headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    if int(pagina_atual) > 1 and itens_ordenados_cache:
        try:
            itens_ordenados = json.loads(itens_ordenados_cache)
        except Exception:
            itens_ordenados = []
        try:
            mapa_id = json.loads(mapa_id_json) if mapa_id_json else {}
        except Exception:
            mapa_id = {}
    else:
        query_url = f"{NOTION_API_URL}/databases/0ce7b9883c49441eb6852a69e6894667/query"
        payload_notion = {
            "filter": {
                "and": [
                    {"property": "Tipo", "select": {"equals": tipo_selecionado}},
                    {"property": "Estoque", "number": {"greater_than": 0}},
                ]
            },
            "sorts": [{"property": "ID", "direction": "ascending"}],
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                query_url, json=payload_notion, headers=notion_headers
            )

        results = response.json().get("results", [])
        itens_filtrados = []
        for page in results:
            props = page.get("properties", {})

            def get_text(p):
                return (
                    (
                        props.get(p, {}).get("rich_text", [])
                        or props.get(p, {}).get("title", [])
                    )[0].get("plain_text", "")
                    if (
                        props.get(p, {}).get("rich_text", [])
                        or props.get(p, {}).get("title", [])
                    )
                    else ""
                )

            indice = get_text("Índice")
            if not indice:
                continue

            itens_filtrados.append(
                {
                    "ID": get_text("ID"),
                    "Nome": get_text("Nome"),
                    "Preço": props.get("Preço", {}).get("number", 0) or 0,
                    "Preço Promo": props.get("Preço Promo", {}).get(
                        "number", 0
                    )
                    or 0,
                    "Estoque": props.get("Estoque", {}).get("number", 0) or 0,
                    "Tipo": props.get("Tipo", {})
                    .get("select", {})
                    .get("name", ""),
                    "Índice": indice,
                    "Medida": get_text("Medida"),
                    "Descrição": get_text("Descrição"),
                    "Em Promo": props.get("Em Promo", {}).get(
                        "checkbox", False
                    ),
                }
            )

        itens_ordenados = sorted(
            itens_filtrados,
            key=lambda x: (
                int(x["Índice"]) if str(x["Índice"]).isdigit() else 0
            ),
        )

    start_index = (int(pagina_atual) - 1) * itens_por_pagina
    itens_da_pagina = itens_ordenados[start_index : start_index + itens_por_pagina]

    menu_texto = (
        f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_*{primeiro_nome}*_, Aqui estão as\n"
        + (
            f"*Trufas de Colher* disponíveis hoje\nna categoria (🍫 *Individuais*):\n\n"
            if tipo_selecionado == "Individuais"
            else f"*Opções* disponíveis hoje\nna categoria (📦 *Combos*):\n\n"
        )
        if int(pagina_atual) == 1
        else f"Aqui está a continuação\ndo cardápio na categoria *{tipo_selecionado}*:\n\n"
    )

    for item in itens_da_pagina:
        preco_val, preco_promo_val = float(item["Preço"] or 0), float(
            item["Preço Promo"] or 0
        )
        preco_str = (
            f"R$ {preco_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        preco_promo_str = (
            f"R$ {preco_promo_val:,.2f}".replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

        linha = (
            f"*{item['Índice']})*"
            + (
                " 🎁"
                if item["Em Promo"]
                else (" 🍫" if tipo_selecionado == "Individuais" else " 📦")
            )
            + f" {item['Nome']}"
            + (f" ({item['Medida']})" if item["Medida"] else "")
        )
        linha += "\n_*Preço:*_ " + (
            f"~{preco_str}~ *{preco_promo_str}*"
            if item["Em Promo"] and preco_promo_val > 0
            else f"*{preco_str}*"
        )

        if item["Descrição"]:
            linha += f"\n_*Descrição:*_\n_{item['Descrição'].strip()}_"
        menu_texto += (
            linha + "\n\n----------------------------------------------------------\n\n"
        )

        mapa_id[str(item["Índice"])] = {
            "id": item["ID"],
            "nome": item["Nome"],
            "preco": preco_promo_val if preco_promo_val > 0 else preco_val,
            "estq": item["Estoque"],
        }

    menu_texto += "ㅤ"
    tem_mais_itens = (start_index + itens_por_pagina) < len(itens_ordenados)

    if not itens_da_pagina:
        menu_texto = (
            f"🚫 Desculpe, não temos nenhum item disponível na categoria *{tipo_selecionado}* no momento."
            if int(pagina_atual) == 1
            else "Não há mais itens para mostrar."
        )

    estado_conversacao = (
        "calcula_cupom"
        if modo_cupom
        else ("visualizando_cardapio3" if tem_mais_itens else "visualizando_cardapio")
    )

    sql_update_str = f"UPDATE conversas_bot SET estado_conversa = '{estado_conversacao}', expirando = FALSE, mapa_id_json = '{json.dumps(mapa_id)}', pagina_atual = {pagina_atual}, categoria_selecionada = '{tipo_selecionado}', ultima_interacao = NOW() WHERE jid = '{user_id}';"

    if tem_mais_itens and not modo_cupom:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": ""},
                "body": {
                    "text": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_*{primeiro_nome}*_, que tal adicionar itens do nosso cardápio à sacola? 🛍️\n"
                },
                "footer": {
                    "text": "Clique no botão abaixo e escolha a opção desejada:"
                },
                "action": {
                    "button": "VER OPÇÕES",
                    "sections": [
                        {
                            "title": "Opções Principais",
                            "rows": [
                                {"id": "1", "title": "➕ Ver Mais (Itens)"},
                                {"id": "2", "title": "🛍️ Adicionar à Sacola"},
                                {"id": "3", "title": "🔰 Cardápios"},
                                {"id": "4", "title": "❌ Sair"},
                            ],
                        }
                    ],
                },
            },
        }
    else:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_*{primeiro_nome}*_,\n\n{menu_texto}\n\n_🙂 Escolha qual o próximo passo:_\n"
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "1",
                                "title": f"Ver → {'📦 Combos' if tipo_selecionado == 'Individuais' else '🍫 Individuais'}",
                            },
                        },
                        {
                            "type": "reply",
                            "reply": {"id": "2", "title": "⏮️ Menu Principal"},
                        },
                        {"type": "reply", "reply": {"id": "3", "title": "❌ Sair"}},
                    ]
                },
            },
        }

    return {"sql_update": sql_update_str, "payload": payload}
