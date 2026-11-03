import json
import asyncio

# IMPORTAÇÃO CORRIGIDA: Agora chama a busca do cardápio para gerar o menu!
from subfluxos.cardapio import processar_busca_cardapio
from subfluxos.cliente_retorna_menu import processar_retorno_menu


async def processar_aguardando_categoria(
    jid, telefone_real, primeiro_nome, entrada_cliente, cliente_db
):
    entrada = str(entrada_cliente).strip().lower()

    if entrada in ["3", "menu", "menu principal", "voltar", "início", "inicio"]:
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

    categoria = None
    if entrada in ["1", "individuais", "individual", "trufas", "trufa"]:
        categoria = "Individuais"
    elif entrada in ["2", "combos", "combo"]:
        categoria = "Combos"

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

    # ROTA CORRETA: Chama o cardápio no Notion para exibir os produtos.
    # O próprio processar_busca_cardapio já atualiza o estado para "visualizando_cardapio" no banco.
    resultado = await processar_busca_cardapio(
        user_id=jid,
        telefone_real=telefone_real,
        primeiro_nome=primeiro_nome,
        tipo_selecionado=categoria,
        pagina_atual=1,
        mapa_id_json="{}",
    )

    return resultado
