import json
import httpx
import os
from subfluxos.calculo_pedido import processar_calculo_pedido
from config.database import obter_conexao, liberar_conexao


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

    # =========================================================================
    # CORREÇÃO: Busca as listas sempre frescas diretamente no banco de dados.
    # =========================================================================
    conexao = await obter_conexao()
    try:
        row = await conexao.fetchrow(
            "SELECT itens_a_processar, mapa_id_json, carrinho_json, indice_item_atual FROM conversas_bot WHERE jid = $1",
            user_id,
        )
    finally:
        await liberar_conexao(conexao)

    if not row:
        return {"sql_update": None}

    indice_atual = int(row.get("indice_item_atual") or 0)
    itens_raw = row.get("itens_a_processar")
    mapa_raw = row.get("mapa_id_json")
    carrinho_raw = row.get("carrinho_json")

    # Tratamento da lista de Itens
    if isinstance(itens_raw, str):
        try:
            itens_a_processar = json.loads(itens_raw)
        except Exception:
            if itens_raw.startswith("{"):
                itens_a_processar = [
                    i.strip() for i in itens_raw.strip("{}").split(",")
                ]
            else:
                itens_a_processar = []
    elif isinstance(itens_raw, list):
        itens_a_processar = itens_raw
    else:
        itens_a_processar = []

    # Tratamento do Mapa ID
    if isinstance(mapa_raw, str):
        try:
            mapa_id = json.loads(mapa_raw)
        except Exception:
            mapa_id = {}
    elif isinstance(mapa_raw, dict):
        mapa_id = mapa_raw
    else:
        mapa_id = {}

    # Tratamento do Carrinho
    if isinstance(carrinho_raw, str):
        try:
            carrinho = json.loads(carrinho_raw)
        except Exception:
            carrinho = []
    elif isinstance(carrinho_raw, list):
        carrinho = carrinho_raw
    else:
        carrinho = []

    # Proteção contra lista vazia
    if not itens_a_processar:
        return {
            "sql_update": f"UPDATE conversas_bot SET estado_conversa = 'aguardando_categoria' WHERE jid = '{user_id}';",
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "text",
                "text": {
                    "body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\nOcorreu um erro ao identificar a sua escolha. Por favor, reinicie a escolha da categoria."
                },
            },
        }

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

    if indice_atual >= len(itens_a_processar):
        indice_atual = 0

    item_atual_numero = str(itens_a_processar[indice_atual])
    item_atual_info = mapa_id.get(item_atual_numero, {})

    id_real = item_atual_info.get("id")
    page_id_notion = item_atual_info.get("page_id")
    nome_item = item_atual_info.get("nome", "Item")
    preco_unitario = float(item_atual_info.get("preco", 0))
    estoque_disponivel = int(item_atual_info.get("estq", 0))

    item_no_carrinho = next(
        (
            item
            for item in carrinho
            if str(item.get("Indice", item.get("indice"))) == item_atual_numero
        ),
        None,
    )
    qtd_anterior = int(item_no_carrinho.get("qtd", 0)) if item_no_carrinho else 0

    if nova_quantidade > 0:
        diferenca = nova_quantidade - qtd_anterior
    else:
        diferenca = -qtd_anterior

    if diferenca > estoque_disponivel:
        mensagem_estoque = (
            f"Ops! 😟 O estoque é insuficiente para esta quantidade:\n\n"
            f"*{item_atual_numero}.* {nome_item} - R$ {preco_unitario:.2f}:\n\n"
            f"Temos apenas mais *{estoque_disponivel}* unidades em estoque além das que já pediu.\n\n"
            "Por favor, envie a nova quantidade total desejada deste item.\n\n"
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

    # ==============================================================
    # ATUALIZAÇÃO IMEDIATA NO NOTION API (Abate/Devolve Estoque)
    # ==============================================================
    if diferenca != 0:
        if not page_id_notion:
            print(f"❌ Erro Notion: page_id não encontrado para o item {id_real}.")
        else:
            novo_estoque = estoque_disponivel - diferenca

            NOTION_TOKEN = os.getenv("NOTION_API_KEY", "")
            notion_headers = {
                "Authorization": f"Bearer {NOTION_TOKEN}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            }
            notion_payload = {"properties": {"Estoque": {"number": novo_estoque}}}

            try:
                async with httpx.AsyncClient() as client:
                    res = await client.patch(
                        f"https://api.notion.com/v1/pages/{page_id_notion}",
                        json=notion_payload,
                        headers=notion_headers,
                    )
                    if res.status_code == 200:
                        mapa_id[item_atual_numero]["estq"] = novo_estoque
                        print(
                            f"✅ Estoque de '{nome_item}' atualizado no Notion para {novo_estoque}."
                        )
                    else:
                        print(
                            f"❌ Erro Notion Estoque HTTP {res.status_code}: {res.text}"
                        )
            except Exception as e:
                print(f"❌ Exceção ao atualizar estoque no Notion: {e}")

    # Atualiza o carrinho (MUDANÇA: a chave volta a ser "indice" minúsculo para padrão)
    if item_no_carrinho:
        if nova_quantidade > 0:
            item_no_carrinho["qtd"] = nova_quantidade
        else:
            carrinho = [
                item
                for item in carrinho
                if str(item.get("Indice", item.get("indice"))) != item_atual_numero
            ]
    elif nova_quantidade > 0:
        carrinho.append(
            {
                "indice": item_atual_numero,
                "id": id_real,
                "nome": nome_item,
                "qtd": nova_quantidade,
                "precoUnitario": preco_unitario,
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

        mapa_id_json_str = json.dumps(mapa_id, ensure_ascii=False).replace("'", "''")
        carrinho_json_str = json.dumps(carrinho, ensure_ascii=False).replace("'", "''")

        sql_update = f"UPDATE conversas_bot SET carrinho_json = '{carrinho_json_str}', mapa_id_json = '{mapa_id_json_str}', indice_item_atual = {proximo_indice}, expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{user_id}';"

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
        mapa_id_json_str = json.dumps(mapa_id, ensure_ascii=False).replace("'", "''")

        sql_update = f"UPDATE conversas_bot SET estado_conversa = 'calcula_pedido', carrinho_json = '{carrinho_json_str}', mapa_id_json = '{mapa_id_json_str}', itens_a_processar = NULL, expirando = FALSE, indice_item_atual = NULL, ultima_interacao = NOW() WHERE jid = '{user_id}';"

        dados_atualizados = dados_estado.copy()
        dados_atualizados["carrinho_json"] = carrinho_json_str
        dados_atualizados["mapa_id_json"] = mapa_id_json_str

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
