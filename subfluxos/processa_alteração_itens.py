import json
from subfluxos.calculo_pedido import processar_calculo_pedido


async def processando_alteracao_itens(
    user_id, telefone_real, mensagem_cliente, dados_estado
):
    try:
        nova_quantidade = int(str(mensagem_cliente).strip())
        if nova_quantidade < 0:
            raise ValueError
    except ValueError:
        return {
            "sql_update": None,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "text",
                "text": {
                    "body": "_*👸🏾 Kakaw - TheLordTrufas.*_\n\nPor favor, digite uma\nquantidade válida.😕"
                },
            },
        }

    indice_atual = int(dados_estado.get("indice_item_atual", 0))

    itens_raw = dados_estado.get("itens_a_processar", "")
    if isinstance(itens_raw, str) and itens_raw.startswith("{"):
        itens_a_processar = [i.strip() for i in itens_raw.strip("{}").split(",")]
    else:
        try:
            itens_a_processar = (
                json.loads(itens_raw) if isinstance(itens_raw, str) else itens_raw
            )
        except Exception:
            itens_a_processar = []

    mapa_raw = dados_estado.get("mapa_id_json", "{}")
    try:
        mapa_id = json.loads(mapa_raw) if isinstance(mapa_raw, str) else mapa_raw
    except Exception:
        mapa_id = {}

    carrinho_raw = dados_estado.get("carrinho_json", "[]")
    try:
        carrinho = (
            json.loads(carrinho_raw) if isinstance(carrinho_raw, str) else carrinho_raw
        )
    except Exception:
        carrinho = []
    if not isinstance(carrinho, list):
        carrinho = []

    for item_num in itens_a_processar:
        if str(item_num) not in mapa_id:
            mensagem_erro = "*⚠️ Atenção:* Algum *ITEM* escolhido\nnão existe no *CARDÁPIO*.\nPor favor, observe o cardápio novamente, e escolha os\nitens corretamente.\n\n----------------------------------------------------------\n\nPara escolher é muito simples,\nbasta enviar o *NÚMERO*\nreferente ao *ITEM*\nno *CARDÁPIO*.\n\n_Para *ADICIONAR MAIS*_\n_*DE UM* item, envie os_\n_números *SEPARADOS POR VÍRGULA*:_\n\n*(Exemplo: 5, 10, 3)*"
            sql_update_erro = f"UPDATE conversas_bot SET estado_conversa = 'aguardando_escolha_item', itens_a_processar = NULL, expirando = FALSE, indice_item_atual = NULL, ultima_interacao = NOW() WHERE jid = '{user_id}';"
            return {
                "sql_update": sql_update_erro,
                "payload": {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": telefone_real,
                    "type": "text",
                    "text": {
                        "body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n{mensagem_erro}"
                    },
                },
            }

    item_atual_numero = str(itens_a_processar[indice_atual])
    item_atual_info = mapa_id.get(item_atual_numero)

    if item_atual_info:
        item_no_carrinho = next(
            (
                item
                for item in carrinho
                if str(item.get("Indice", item.get("indice"))) == item_atual_numero
            ),
            None,
        )
        if item_no_carrinho:
            item_no_carrinho["qtd"] = nova_quantidade
        elif nova_quantidade > 0:
            carrinho.append(
                {
                    "Indice": item_atual_numero,
                    "id": item_atual_info.get("id"),
                    "nome": item_atual_info.get("nome"),
                    "qtd": nova_quantidade,
                    "precoUnitario": item_atual_info.get("preco"),
                }
            )

    proximo_indice = indice_atual + 1

    if proximo_indice < len(itens_a_processar):
        proximo_item_numero = str(itens_a_processar[proximo_indice])
        proximo_item_info = mapa_id.get(proximo_item_numero, {})
        nome_proximo_item = proximo_item_info.get("nome", "Item Desconhecido")

        proximo_no_carrinho = next(
            (
                item
                for item in carrinho
                if item.get("id") == proximo_item_info.get("id")
            ),
            None,
        )
        qtd_proximo = proximo_no_carrinho.get("qtd") if proximo_no_carrinho else 0

        preco_num = float(proximo_item_info.get("preco", 0))
        preco_formatado = (
            f"R$ {preco_num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        estoque_atual = proximo_item_info.get("estq", 0)

        mensagem_resposta = f"Ok ✍️. E qual a nova quantidade\npara o item a seguir:\n\n*{proximo_item_numero})* "
        if "combo" in nome_proximo_item.lower():
            mensagem_resposta += f"📦 {nome_proximo_item}\n\n"
        else:
            mensagem_resposta += f"🍫 {nome_proximo_item}\n\n"

        mensagem_resposta += f'*Preço:* {preco_formatado}\n\n*Qtde. Atual:* {qtd_proximo}\n*Estoque:* {estoque_atual}\n\n----------------------------------------------------\n\nPara *REMOVER* o item\né só digitar *"0"*\n\nPara *MANTER* o item\né só digitar a mesma\n*QUANTIDADE ATUAL*\n'

        sql_update = f"UPDATE conversas_bot SET carrinho_json = '{json.dumps(carrinho, ensure_ascii=False)}', indice_item_atual = {proximo_indice}, expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{user_id}';"

        return {
            "sql_update": sql_update,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "text",
                "text": {
                    "body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n{mensagem_resposta}"
                },
            },
        }
    else:
        carrinho_final = [item for item in carrinho if item.get("qtd", 0) > 0]
        carrinho_json_str = json.dumps(carrinho_final, ensure_ascii=False).replace(
            "'", "''"
        )

        sql_update = f"UPDATE conversas_bot SET estado_conversa = 'calcula_pedido', carrinho_json = '{carrinho_json_str}', itens_a_processar = NULL, expirando = FALSE, indice_item_atual = NULL, ultima_interacao = NOW() WHERE jid = '{user_id}';"

        # Usar o subfluxo em vez de action invisível
        dados_atualizados = dados_estado.copy()
        dados_atualizados["carrinho_json"] = carrinho_json_str

        primeiro_nome = dados_estado.get("primeiro_nome", "Cliente")
        resultado_calculo = await processar_calculo_pedido(
            user_id, telefone_real, primeiro_nome, dados_atualizados
        )

        sql_final = [sql_update]
        if isinstance(resultado_calculo.get("sql_update"), list):
            sql_final.extend(resultado_calculo["sql_update"])
        elif resultado_calculo.get("sql_update"):
            sql_final.append(resultado_calculo["sql_update"])

        resultado_calculo["sql_update"] = sql_final
        return resultado_calculo
