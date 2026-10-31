import json
import logging

logger = logging.getLogger(__name__)


async def processar_escolha_item(
    user_id: str,
    telefone_real: str,
    primeiro_nome: str,
    mensagem_cliente: str,
    categoria_selecionada: str,
    mapa_id_json_str: str,
) -> dict:
    """
    [MÓDULO 1.24 - Aguardando Escolha Item Cupom]
    Valida os números enviados pelo cliente na seleção de itens com cupom/cardápio,
    verifica se existem no mapa, trata listas separadas por vírgula e direciona
    para a quantidade do item ou montagem de combo.
    """
    logger.info(
        "Escolha Item Cupom | JID: %s | Mensagem: '%s' | Categoria: %s",
        user_id,
        mensagem_cliente,
        categoria_selecionada,
    )

    # 1. Limpa e divide os itens enviados (ex: "7, 9, 15" -> ["7", "9", "15"])[cite: 28]
    itens_brutos = str(mensagem_cliente).replace(" ", "").split(",")
    itens_validos = [i for i in itens_brutos if i and i.isdigit()]

    # Se o cliente mandou algo inválido (letras, símbolos)[cite: 28]
    if not itens_validos:
        mensagem_erro = (
            "Por favor, envie uma lista\n"
            "de números válidos\n"
            "separados por vírgula\n\n"
            "_*(Exemplo: 7, 9, 15)*_."
        )
        sql_update = f"""
            UPDATE conversas_bot 
            SET estado_conversa = 'aguardando_escolha_item_cupom', 
                itens_a_processar = NULL, 
                expirando = FALSE, 
                indice_item_atual = NULL, 
                ultima_interacao = NOW() 
            WHERE jid = '{user_id}';
        """
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real if telefone_real else user_id,
            "type": "text",
            "text": {"body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n{mensagem_erro}"},
        }
        return {"status": "erro", "sql_update": sql_update, "payload": payload}

    # 2. Carrega o mapa de IDs do cardápio[cite: 28]
    try:
        mapa_id = json.loads(mapa_id_json_str) if mapa_id_json_str else {}
    except Exception:
        mapa_id = {}

    # 3. Valida se todos os números escolhidos existem no mapa[cite: 28]
    indices_validos = True
    for item_num in itens_validos:
        if item_num not in mapa_id:
            indices_validos = False
            break

    # Se algum item não existir no cardápio atual[cite: 28]
    if not indices_validos:
        mensagem_atencao = (
            f"*⚠️ Atenção:* Algum *ITEM* escolhido\nnão existe no *CARDÁPIO*.\n"
            "Por favor, observe o cardápio novamente, e escolha os\nitens"
            " corretamente.\n\n----------------------------------------------------------\n\nPara"
            " escolher é muito simples,\nbasta enviar o *NÚMERO*\nreferente ao"
            " *ITEM*\nno *CARDÁPIO*.\n\n_Para *ADICIONAR MAIS*_\n_*DE UM* item,"
            " envie os_\n_números *SEPARADOS POR VÍRGULA*:_\n\n*(Exemplo: 5, 10,"
            " 3)*"
        )
        sql_update = f"""
            UPDATE conversas_bot 
            SET estado_conversa = 'aguardando_escolha_item_cupom', 
                itens_a_processar = NULL, 
                expirando = FALSE, 
                indice_item_atual = NULL, 
                ultima_interacao = NOW() 
            WHERE jid = '{user_id}';
        """
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real if telefone_real else user_id,
            "type": "text",
            "text": {"body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n{mensagem_atencao}"},
        }
        return {"status": "erro", "sql_update": sql_update, "payload": payload}

    # 4. Processa o primeiro item válido da lista[cite: 28]
    primeiro_item_num = itens_validos[0]
    primeiro_item_info = mapa_id[primeiro_item_num]
    nome_item = primeiro_item_info.get("nome", "Item Desconhecido")
    preco_numerico = primeiro_item_info.get("preco", 0)

    # Formatação de preço em BRL[cite: 28]
    preco_formatado = (
        f"R$ {preco_numerico:,.2f}".replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )

    # Verifica se é um Combo ou Individual[cite: 28]
    eh_combo = "combo" in nome_item.lower() or categoria_selecionada == "Combos"

    # Salva a lista de itens a processar no array postgres e pede a quantidade[cite: 28]
    itens_array_sql = "{" + ",".join(itens_validos) + "}"
    sql_update = f"""
        UPDATE conversas_bot 
        SET estado_conversa = 'processando_lista_itens', 
            itens_a_processar = '{itens_array_sql}'::text[], 
            indice_item_atual = 0, 
            expirando = FALSE, 
            ultima_interacao = NOW() 
        WHERE jid = '{user_id}';
    """

    if "combo" in nome_item.lower():
        mensagem_resposta = (
            f"_*{primeiro_nome}*_, adicionei os itens que\nvocê"
            f" escolheu.😉\n\nQual a quantidade para o"
            f" item:\n\n*{primeiro_item_num})* 📦 {nome_item}\n\n_*Preço:*_ *"
            f"{preco_formatado}*\n\n_*(Exemplo: 4)*_\n"
        )
    else:
        mensagem_resposta = (
            f"_*{primeiro_nome}*_, adicionei os itens que\nvocê"
            f" escolheu.😉\n\nQual a quantidade para o"
            f" item:\n\n*{primeiro_item_num})* 🍫 {nome_item}\n\n_*Preço:*_ *"
            f"{preco_formatado}*\n\n_*(Exemplo: 1)*_\n"
        )

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": telefone_real if telefone_real else user_id,
        "type": "text",
        "text": {"body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n{mensagem_resposta}"},
    }

    return {
        "status": "sucesso",
        "sql_update": sql_update,
        "proximo_estado": ("processando_lista_itens"),
        "payload": payload,
    }
