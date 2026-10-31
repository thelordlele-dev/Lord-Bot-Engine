import json
from subfluxos.calculo_pedido import processar_calculo_pedido


async def processar_quantidade_item(
    user_id, telefone_real, primeiro_nome, mensagem_cliente, estado_atual_db
):
    print(
        f"📦 Processando Quantidade Unificada | JID: {user_id} | Qtd Informada: '{mensagem_cliente}'"
    )

    try:
        nova_quantidade = int(str(mensagem_cliente).strip())
    except ValueError:
        nova_quantidade = -1

    if nova_quantidade < 0:
        return {
            "sql_update": None,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "text",
                "text": {
                    "body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\nPor favor, digite uma\nquantidade válida.😕"
                },
            },
        }

    indice_atual = int(estado_atual_db.get("indice_item_atual", 0))

    itens_a_processar = estado_atual_db.get("itens_a_processar")
    if isinstance(itens_a_processar, str):
        try:
            itens_a_processar = json.loads(itens_a_processar)
        except Exception:
            itens_a_processar = []
    if not isinstance(itens_a_processar, list):
        itens_a_processar = []

    mapa_id = estado_atual_db.get("mapa_id_json")
    if isinstance(mapa_id, str):
        try:
            mapa_id = json.loads(mapa_id)
        except Exception:
            mapa_id = {}
    if not isinstance(mapa_id, dict):
        mapa_id = {}

    carrinho = estado_atual_db.get("carrinho_json")
    if isinstance(carrinho, str):
        try:
            carrinho = json.loads(carrinho)
        except Exception:
            carrinho = []
    if not isinstance(carrinho, list):
        carrinho = []

    for item_num in itens_a_processar:
        if str(item_num) not in mapa_id:
            mensagem_atencao = (
                "*⚠️ Atenção:* Algum *ITEM* escolhido\nnão existe no *CARDÁPIO*.\n"
                "Por favor, observe o cardápio novamente, e escolha os\nitens corretamente.\n\n"
                "----------------------------------------------------------\n\n"
                "Para escolher é muito simples,\nbasta enviar o *NÚMERO*\n"
                "referente ao *ITEM* no *CARDÁPIO*."
            )
            return {
                "sql_update": f"UPDATE conversas_bot SET estado_conversa = 'aguardando_escolha_item', itens_a_processar = NULL, indice_item_atual = NULL WHERE jid = '{user_id}';",
                "payload": {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": telefone_real,
                    "type": "text",
                    "text": {
                        "body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n{mensagem_atencao}"
                    },
                },
            }

    if indice_atual >= len(itens_a_processar):
        indice_atual = 0

    item_atual_numero = str(itens_a_processar[indice_atual])
    item_atual_info = mapa_id.get(item_atual_numero, {})

    id_real = item_atual_info.get("id")
    nome_item = item_atual_info.get("nome", "Item")
    preco_unitario = float(item_atual_info.get("preco", 0))
    estoque_disponivel = int(item_atual_info.get("estq", 0))

    if nova_quantidade > estoque_disponivel:
        mensagem_estoque = (
            f"Ops! 😟 Alguns itens não têm\nestoque suficiente:\n\n"
            f"*{item_atual_numero}.* {nome_item} - R$ {preco_unitario:.2f}:\n\n"
            f"Só temos *{estoque_disponivel}* em estoque.\n\n"
            "Por favor, envie a nova quantidade deste item.\n\n"
            '_*(Digite "0" para remover o item)*_\n'
        )
        return {
            "sql_update": None,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "text",
                "text": {
                    "body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n{mensagem_estoque}"
                },
            },
        }

    item_no_carrinho = next((i for i in carrinho if i.get("id") == id_real), None)

    if item_no_carrinho:
        if nova_quantidade > 0:
            item_no_carrinho["qtd"] = nova_quantidade
        else:
            carrinho = [i for i in carrinho if i.get("id") != id_real]
    else:
        if nova_quantidade > 0:
            carrinho.append(
                {
                    "indice": item_atual_numero,
                    "id": id_real,
                    "nome": nome_item,
                    "qtd": nova_quantidade,
                    "precoUnitario": f"{preco_unitario:.2f}",
                }
            )

    carrinho_atualizado = [i for i in carrinho if i.get("qtd", 0) > 0]
    carrinho_json_str = json.dumps(carrinho_atualizado)

    proximo_indice = indice_atual + 1

    if proximo_indice < len(itens_a_processar):
        proximo_item_numero = str(itens_a_processar[proximo_indice])
        proximo_item_info = mapa_id.get(proximo_item_numero, {})
        nome_proximo = proximo_item_info.get("nome", "Item")
        preco_proximo = float(proximo_item_info.get("preco", 0))
        estoque_proximo = int(proximo_item_info.get("estq", 0))

        preco_formatado = (
            f"R$ {preco_proximo:,.2f}".replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

        mensagem_proximo = (
            f"Ok ✍️. E qual a quantidade\npara o item a seguir:\n\n"
            f"*{proximo_item_numero})* 🍫 {nome_proximo}\n\n"
            f"_*Preço:*_ *{preco_formatado}*\n"
            f"_*Estoque:*_ *{estoque_proximo}*\n\n"
            "_*(Exemplo: 3)*_\n"
        )

        sql_atualizacao = f"UPDATE conversas_bot SET carrinho_json = '{carrinho_json_str.replace('\'', '\'\'')}', indice_item_atual = {proximo_indice}, expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{user_id}';"

        return {
            "sql_update": sql_atualizacao,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "text",
                "text": {
                    "body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n{mensagem_proximo}"
                },
            },
        }
    else:
        sql_atualizacao = f"UPDATE conversas_bot SET estado_conversa = 'calcula_pedido', carrinho_json = '{carrinho_json_str.replace('\'', '\'\'')}', itens_a_processar = NULL, indice_item_atual = NULL, expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{user_id}';"

        dados_atualizados = estado_atual_db.copy()
        dados_atualizados["carrinho_json"] = carrinho_json_str

        resultado_calculo = await processar_calculo_pedido(
            user_id, telefone_real, primeiro_nome, dados_atualizados
        )

        sql_final = [sql_atualizacao]
        if isinstance(resultado_calculo.get("sql_update"), list):
            sql_final.extend(resultado_calculo["sql_update"])
        elif resultado_calculo.get("sql_update"):
            sql_final.append(resultado_calculo["sql_update"])

        resultado_calculo["sql_update"] = sql_final
        return resultado_calculo
