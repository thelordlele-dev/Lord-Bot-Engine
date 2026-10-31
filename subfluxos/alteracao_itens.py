import json


async def processar_alteracao_itens(
    user_id, telefone_real, primeiro_nome, mensagem_cliente, dados_estado
):
    """
    [MÓDULO DE ALTERAÇÃO DE ITENS]
    Recebe os índices dos itens que o cliente deseja alterar, valida no cardápio,
    e inicia o loop de processamento para alterar as quantidades[cite: 26].
    """
    # 1. Limpeza e extração dos itens enviados (ex: "7, 9" -> ["7", "9"])
    itens_brutos = str(mensagem_cliente).replace(" ", "").split(",")
    itens_validos = [i for i in itens_brutos if i and i.isdigit()]

    if not itens_validos:
        mensagem_erro = (
            "Por favor, envie uma lista\n"
            "de números válidos\n"
            "separados por vírgula:\n\n"
            "_*(Exemplo: 7, 9, 15)*_\n"
        )
        return {
            "proximo_estado": "aguardando_alteracao_item",
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "text",
                "text": {"body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n{mensagem_erro}"},
            },
        }

    # 2. Carrega o mapa de IDs e o carrinho atual da base de dados
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

    # 3. Processa o primeiro item da lista para iniciar a alteração[cite: 26]
    primeiro_item_numero = itens_validos[0]
    primeiro_item_info = mapa_id.get(primeiro_item_numero)

    if not primeiro_item_info:
        mensagem_erro_item = f"O item número {primeiro_item_numero} não foi encontrado. Por favor, tente novamente[cite: 26]."
        return {
            "proximo_estado": "aguardando_alteracao_item",
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "text",
                "text": {
                    "body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n{mensagem_erro_item}"
                },
            },
        }

    # 4. Encontra o item no carrinho para obter a quantidade atual[cite: 26]
    id_item = primeiro_item_info.get("id")
    item_no_carrinho = next(
        (item for item in carrinho if item.get("id") == id_item), None
    )
    quantidade_atual = item_no_carrinho.get("qtd") if item_no_carrinho else 0

    preco_numerico = float(primeiro_item_info.get("preco", 0.0))
    preco_formatado = (
        f"R$ {preco_numerico:,.2f}".replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )
    nome_item = primeiro_item_info.get("nome", "Item Desconhecido")

    # 5. Monta a mensagem final para o cliente[cite: 26]
    mensagem_resposta = (
        f"_*{primeiro_nome}*_,\n"
        "anotei os itens que você deseja alterar. 🧐\n\n"
        "Qual a nova quantidade\n"
        "para o item a seguir:\n\n"
        f"*{primeiro_item_numero})* "
    )

    if "combo" in nome_item.lower():
        mensagem_resposta += f"📦 {nome_item}\n\n"
    else:
        mensagem_resposta += f"🍫 {nome_item}\n\n"

    mensagem_resposta += (
        f"*Preço:* {preco_formatado}\n"
        f"*Qtde. Atual:* {quantidade_atual}\n\n"
        "----------------------------------------------------\n\n"
        "Para *REMOVER* o item\n"
        'é só digitar *"0"*\n\n'
        "Para *MANTER* o item\n"
        "é só digitar a mesma\n"
        "*QUANTIDADE ATUAL*\n"
    )

    # 6. Prepara o SQL para salvar a lista de alterações pendentes e avançar o estado[cite: 26]
    itens_formatados_sql = "{" + ",".join(itens_validos) + "}"
    sql_update = f"""
        UPDATE conversas_bot
        SET estado_conversa = 'processando_alteracao_itens',
            itens_a_processar = '{itens_formatados_sql}',
            indice_item_atual = 0,
            expirando = FALSE,
            ultima_interacao = NOW()
        WHERE jid = '{user_id}'
    """

    return {
        "proximo_estado": "processando_alteracao_itens",
        "sql_update": sql_update.strip(),
        "payload": {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real,
            "type": "text",
            "text": {"body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n{mensagem_resposta}"},
        },
    }
