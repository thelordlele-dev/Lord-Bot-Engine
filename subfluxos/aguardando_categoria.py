import json
import asyncio

# ==============================================================
# IMPORTAÇÕES GLOBAIS (No topo para o Python nunca perder)
# ==============================================================
from subfluxos.navegacao_cardapio import processar_navegacao_cardapio
from subfluxos.cliente_retorna_menu import processar_retorno_menu


async def processar_aguardando_categoria(
    jid, telefone_real, primeiro_nome, entrada_cliente, cliente_db
):
    entrada = str(entrada_cliente).strip().lower()

    # ==============================================================
    # OPÇÃO 3: VOLTAR AO MENU PRINCIPAL
    # ==============================================================
    if entrada in ["3", "menu", "menu principal", "voltar", "início", "inicio"]:

        # Chama a função que devolve o menu na tela (usando jid, jid para manter o padrão)
        resultado = processar_retorno_menu(jid, jid, cliente_db)

        if asyncio.iscoroutine(resultado):
            resultado = await resultado

        sql_update = f"UPDATE conversas_bot SET estado_conversa = 'menu_inicio' WHERE jid = '{jid}';"

        if isinstance(resultado, dict):
            if "sql_update" in resultado:
                if isinstance(resultado["sql_update"], list):
                    resultado["sql_update"].append(sql_update)
                else:
                    resultado["sql_update"] = [resultado["sql_update"], sql_update]
            else:
                resultado["sql_update"] = sql_update

        return resultado

    # ==============================================================
    # IDENTIFICA A CATEGORIA (Individuais ou Combos)
    # ==============================================================
    categoria = None
    if entrada in ["1", "individuais", "individual", "trufas", "trufa"]:
        categoria = "Individuais"
    elif entrada in ["2", "combos", "combo"]:
        categoria = "Combos"

    # Se o cliente enviou algo inválido
    if not categoria:
        mensagem = (
            f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n"
            f"_*{primeiro_nome}*_, sua mensagem\n"
            f"não é válida. Por favor escolha\n"
            f"uma das opções abaixo:\n\n"
            f"Clique no botão abaixo e escolha a opção desejada:"
        )
        payload_erro = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real if telefone_real else jid,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": mensagem},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": "1", "title": "🍫 Individuais"},
                        },
                        {"type": "reply", "reply": {"id": "2", "title": "📦 Combos"}},
                        {
                            "type": "reply",
                            "reply": {"id": "3", "title": "⏪ Menu Principal"},
                        },
                    ]
                },
            },
        }
        return {"payload": payload_erro}

    # ==============================================================
    # SE A CATEGORIA FOR VÁLIDA (Inicia a busca no Notion)
    # ==============================================================
    sql_transicao = f"UPDATE conversas_bot SET estado_conversa = 'visualizando_cardapio', categoria_selecionada = '{categoria}', pagina_atual = 1 WHERE jid = '{jid}';"

    cliente_db_temp = cliente_db.copy() if cliente_db else {}
    cliente_db_temp["categoria_selecionada"] = categoria
    cliente_db_temp["pagina_atual"] = 1

    resultado = processar_navegacao_cardapio(
        "visualizando_cardapio", jid, telefone_real, primeiro_nome, "1", cliente_db_temp
    )

    if asyncio.iscoroutine(resultado):
        resultado = await resultado

    comandos_sql = [sql_transicao]
    sql_nav = resultado.get("sql_update")

    if sql_nav:
        if isinstance(sql_nav, list):
            comandos_sql.extend(sql_nav)
        else:
            comandos_sql.append(sql_nav)

    resultado["sql_update"] = comandos_sql

    return resultado
