import logging
import json
from subfluxos.cardapio import processar_busca_cardapio

logger = logging.getLogger(__name__)


async def processar_navegacao_cardapio(
    estado_atual: str,
    opcao_escolhida: str,
    jid: str,
    telefone_real: str,
    primeiro_nome: str,
    categoria_atual: str,
    pagina_atual: int,
    mapa_id_json: dict,
) -> dict:
    opcao = str(opcao_escolhida).strip()

    if opcao == "1" and estado_atual in [
        "visualizando_cardapio3",
        "visualizando_cardapio_cupom3",
    ]:
        nova_pagina = int(pagina_atual) + 1
        modo_cupom = "cupom" in estado_atual
        return await processar_busca_cardapio(
            jid,
            telefone_real,
            primeiro_nome,
            categoria_atual,
            nova_pagina,
            json.dumps(mapa_id_json),
            modo_cupom,
        )

    elif (
        (
            opcao == "1"
            and estado_atual
            in [
                "visualizando_cardapio",
                "visualizando_cardapio2",
                "visualizando_cardapio_cupom2",
            ]
        )
        or (
            opcao == "2"
            and estado_atual
            in ["visualizando_cardapio3", "visualizando_cardapio_cupom3"]
        )
        or (opcao == "1" and estado_atual == "visualizando_cardapio_cupom1")
    ):
        proximo_est = (
            "aguardando_escolha_item_cupom"
            if "cupom" in estado_atual
            else "aguardando_escolha_item"
        )
        sql_update = f"UPDATE conversas_bot SET estado_conversa = '{proximo_est}', expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{jid}';"
        texto_resposta = (
            f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n*_{primeiro_nome}_*,\nchegou a hora de escolher\na(s) _*Trufa(s) de colher*_ que você\n"
            "vai adicionar à sacola. 😜🛍️\n\nPara escolher é muito simples,\nbasta enviar o *NÚMERO*\nreferente ao *ITEM*\nno *CARDÁPIO*.\nㅤ"
        )
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real,
            "type": "text",
            "text": {"body": texto_resposta},
        }
        return {"sql_update": sql_update, "payload": payload}

    elif opcao in ["2", "3"] and estado_atual.startswith("visualizando_cardapio"):
        sql_update = f"UPDATE conversas_bot SET estado_conversa = 'aguardando_categoria', expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{jid}';"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": ""},
                "body": {
                    "text": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n*_{primeiro_nome}_*,\nescolha uma nova categoria para visualizar os itens disponíveis nela\n"
                },
                "footer": {
                    "text": "Clique no botão abaixo e escolha a opção desejada:"
                },
                "action": {
                    "button": "CATEGORIAS",
                    "sections": [
                        {
                            "title": "Opções Principais",
                            "rows": [
                                {"id": "1", "title": "🍫 Individuais"},
                                {"id": "2", "title": "📦 Combos"},
                                {"id": "3", "title": "⏮️ Menu Principal"},
                                {"id": "4", "title": "❌ Sair"},
                            ],
                        }
                    ],
                },
            },
        }
        return {"sql_update": sql_update, "payload": payload}

    return {
        "sql_update": None,
        "payload": {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real,
            "type": "text",
            "text": {
                "body": f"_*_{primeiro_nome}_*_, sua mensagem não é válida para este menu. Por favor, escolha uma das opções exibidas._"
            },
        },
    }
