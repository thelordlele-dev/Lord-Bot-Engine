import json
import httpx
import os
from subfluxos.calculo_pedido import processar_calculo_pedido
from config.database import obter_conexao, liberar_conexao


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
    itens_a_processar = row.get("itens_a_processar")
    mapa_id_str = row.get("mapa_id_json")
    carrinho_str = row.get("carrinho_json")

    if isinstance(itens_a_processar, str):
        try:
            itens_a_processar = json.loads(itens_a_processar)
        except Exception:
            itens_a_processar = []
    if not isinstance(itens_a_processar, list):
        itens_a_processar = []

    if isinstance(mapa_id_str, str):
        try:
            mapa_id = json.loads(mapa_id_str)
        except Exception:
            mapa_id = {}
    elif isinstance(mapa_id_str, dict):
        mapa_id = mapa_id_str
    else:
        mapa_id = {}

    if isinstance(carrinho_str, str):
        try:
            carrinho = json.loads(carrinho_str)
        except Exception:
            carrinho = []
    elif isinstance(carrinho_str, list):
        carrinho = carrinho_str
    else:
        carrinho = []

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
    page_id_notion = item_atual_info.get(
        "page_id"
    )  # <-- O UUID REAL PARA A API DO NOTION
    nome_item = item_atual_info.get("nome", "Item")
    preco_unitario = float(item_atual_info.get("preco", 0))
    estoque_disponivel = int(item_atual_info.get("estq", 0))

    item_no_carrinho = next((i for i in carrinho if i.get("id") == id_real), None)
    qtd_anterior = int(item_no_carrinho.get("qtd", 0)) if item_no_carrinho else 0

    if nova_quantidade > 0:
        diferenca = nova_quantidade - qtd_anterior
    else:
        diferenca = -qtd_anterior

    if diferenca > estoque_disponivel:
        mensagem_estoque = (
            f"Ops! 😟 O estoque é insuficiente para esta quantidade:\n\n"
            f"*{item_atual_numero}.* {nome_item} - R$ {preco_unitario:.2f}:\n\n"
            f"Temos apenas mais *{estoque_disponivel}* unidades em estoque.\n\n"
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
            print(
                f"❌ Erro Notion: page_id não encontrado para o item {id_real}. É necessário gerar o cardápio novamente para atualizar o cache."
            )
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

    # ==============================================================
    # ATUALIZA A SACOLA VIRTUAL DO CLIENTE (Igual ao n8n)
    # ==============================================================
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
    mapa_id_json_str = json.dumps(mapa_id)

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

        # Lógica recuperada do n8n: Emojis dinâmicos baseados no nome!
        icone_proximo = "📦" if "combo" in nome_proximo.lower() else "🍫"

        mensagem_proximo = (
            f"Ok ✍️. E qual a quantidade\npara o item a seguir:\n\n"
            f"*{proximo_item_numero})* {icone_proximo} {nome_proximo}\n\n"
            f"_*Preço:*_ *{preco_formatado}*\n"
            f"_*Estoque:*_ *{estoque_proximo}*\n\n"
            "_*(Exemplo: 3)*_\n"
        )

        sql_atualizacao = f"UPDATE conversas_bot SET carrinho_json = '{carrinho_json_str.replace('\'', '\'\'')}', mapa_id_json = '{mapa_id_json_str.replace('\'', '\'\'')}', indice_item_atual = {proximo_indice}, expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{user_id}';"

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
        sql_atualizacao = f"UPDATE conversas_bot SET estado_conversa = 'calcula_pedido', carrinho_json = '{carrinho_json_str.replace('\'', '\'\'')}', mapa_id_json = '{mapa_id_json_str.replace('\'', '\'\'')}', itens_a_processar = NULL, indice_item_atual = NULL, expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{user_id}';"

        dados_atualizados = estado_atual_db.copy()
        dados_atualizados["carrinho_json"] = carrinho_json_str
        dados_atualizados["mapa_id_json"] = mapa_id_json_str

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
