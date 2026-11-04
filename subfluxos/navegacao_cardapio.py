import logging
import json
import asyncio

from subfluxos.cardapio import processar_busca_cardapio
from subfluxos.cliente_retorna_menu import processar_retorno_menu
from subfluxos.gerenciador_encerramento import processar_encerramento_sessao

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

    opcao = str(opcao_escolhida).strip().lower()

    # 1. ADICIONAR À SACOLA
    if opcao == "nav_add_sacola":
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

    # 2. VER MAIS ITENS (PRÓXIMA PÁGINA)
    elif opcao == "nav_ver_mais":
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

    # 3. VER A OUTRA CATEGORIA DIRETAMENTE (Alterna entre Combo e Individuais)
    elif opcao == "nav_outra_categoria":
        nova_categoria = "Combos" if categoria_atual == "Individuais" else "Individuais"
        resultado = await processar_busca_cardapio(
            jid, telefone_real, primeiro_nome, nova_categoria, 1, "{}", False
        )
        return resultado

    # 4. VOLTAR PARA A LISTA DE CATEGORIAS
    elif opcao == "nav_categorias":
        sql_update = f"UPDATE conversas_bot SET estado_conversa = 'aguardando_categoria', expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{jid}';"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n*_{primeiro_nome}_*,\nescolha uma nova categoria para visualizar os itens disponíveis nela\n"
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "1",
                                "title": "🍫 Individuais",
                            },
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "2",
                                "title": "📦 Combos",
                            },
                        },
                        {
                            "type": "reply",
                            "reply": {"id": "3", "title": "⏮️ Menu Principal"},
                        },
                    ]
                },
            },
        }
        return {"sql_update": sql_update, "payload": payload}

    # 5. VOLTAR AO MENU PRINCIPAL (Corrige o bug da navegação errada!)
    elif opcao == "nav_menu_principal":
        resultado = processar_retorno_menu(jid, jid, {"primeiro_nome": primeiro_nome})
        if asyncio.iscoroutine(resultado):
            resultado = await resultado

        sql_update = f"UPDATE conversas_bot SET estado_conversa = 'menu_inicio', expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{jid}';"

        if isinstance(resultado, dict):
            if "sql_update" in resultado:
                if isinstance(resultado["sql_update"], list):
                    resultado["sql_update"].append(sql_update)
                else:
                    resultado["sql_update"] = [resultado["sql_update"], sql_update]
            else:
                resultado["sql_update"] = sql_update
        return resultado

    # 6. SAIR / ENCERRAR ATENDIMENTO
    elif opcao == "nav_sair":
        resultado = processar_encerramento_sessao(
            jid, telefone_real, primeiro_nome, "[]", "sair"
        )
        if asyncio.iscoroutine(resultado):
            resultado = await resultado
        return resultado

    # CASO O CLIENTE CLIQUE EM ALGO QUE NÃO DEVIA OU DIGITE TEXTO
    return {
        "sql_update": None,
        "payload": {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real,
            "type": "text",
            "text": {
                "body": f"_*_{primeiro_nome}_*_, sua mensagem não é válida para este menu. Por favor, clique numa das opções exibidas no menu anterior._"
            },
        },
    }
