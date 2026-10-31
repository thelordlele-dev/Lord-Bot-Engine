import json
import logging

logger = logging.getLogger(__name__)


async def processar_quantidade_combo(
    user_id: str,
    telefone_real: str,
    primeiro_nome: str,
    mensagem_cliente: str,
    combo_em_montagem_str: str,
    item_pendente_combo_str: str,
    carrinho_json_str: str,
) -> dict:
    try:
        combo = (
            json.loads(combo_em_montagem_str)
            if isinstance(combo_em_montagem_str, str)
            else combo_em_montagem_str or {}
        )
        item_pendente = (
            json.loads(item_pendente_combo_str)
            if isinstance(item_pendente_combo_str, str)
            else item_pendente_combo_str or {}
        )
        carrinho = (
            json.loads(carrinho_json_str)
            if isinstance(carrinho_json_str, str)
            else carrinho_json_str or []
        )
    except Exception:
        sql_erro = f"UPDATE conversas_bot SET estado_conversa = 'menu_inicio', combo_em_montagem = NULL, item_pendente_combo = NULL, ultima_interacao = NOW() WHERE jid = '{user_id}';"
        return {
            "sql_update": sql_erro,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real or user_id,
                "type": "text",
                "text": {
                    "body": "_*👸🏾 Kakaw - TheLordTrufas.*_\n\nErro técnico ao processar o combo. Reiniciando..."
                },
            },
        }

    try:
        quantidade_digitada = int(str(mensagem_cliente).strip())
    except ValueError:
        quantidade_digitada = -1

    if quantidade_digitada <= 0:
        return {
            "sql_update": None,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real or user_id,
                "type": "text",
                "text": {
                    "body": "_*👸🏾 Kakaw - TheLordTrufas.*_\n\nPor favor, digite um número válido."
                },
            },
        }

    etapas = combo.get("etapas", [])
    etapa_atual_idx = combo.get("etapaAtual", 0)

    if etapa_atual_idx >= len(etapas):
        return {
            "sql_update": None,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real or user_id,
                "type": "text",
                "text": {
                    "body": "_*👸🏾 Kakaw - TheLordTrufas.*_\n\nErro no fluxo do combo."
                },
            },
        }

    etapa = etapas[etapa_atual_idx]
    if "escolhidos" not in etapa or not isinstance(etapa["escolhidos"], list):
        etapa["escolhidos"] = []

    limite_sabor = float("inf")
    regra = etapa.get("regra", "")
    if regra and "_por_sabor" in regra:
        try:
            limite_sabor = int(regra.split("_")[0])
        except Exception:
            pass

    ja_tem_mesmo_sabor = sum(
        1 for i in etapa["escolhidos"] if i.get("id") == item_pendente.get("id")
    )
    restante_sabor = limite_sabor - ja_tem_mesmo_sabor

    if ja_tem_mesmo_sabor + quantidade_digitada > limite_sabor:
        msg = f"Você pode adicionar no máximo {restante_sabor} unidade(s) desse item.\n({item_pendente.get('nome')})\n\nEnvie novamente a quantidade."
        return {
            "sql_update": None,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real or user_id,
                "type": "text",
                "text": {"body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n{msg}"},
            },
        }

    total_atual_combo = sum(len(e.get("escolhidos", [])) for e in etapas)
    qtd_necessaria = int(combo.get("qtd_necessaria", 0))
    restante_combo = qtd_necessaria - total_atual_combo

    if total_atual_combo + quantidade_digitada > qtd_necessaria:
        msg = f"Você pode adicionar no máximo {restante_combo} unidade(s) desse item.\n({item_pendente.get('nome')})\n\nEnvie novamente a quantidade."
        return {
            "sql_update": None,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real or user_id,
                "type": "text",
                "text": {"body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n{msg}"},
            },
        }

    for _ in range(quantidade_digitada):
        etapa["escolhidos"].append(
            {
                "id": item_pendente.get("id"),
                "nome": item_pendente.get("nome"),
                "preco_original": item_pendente.get("preco"),
            }
        )

    total_escolhidos_geral = sum(len(e.get("escolhidos", [])) for e in etapas)

    if total_escolhidos_geral >= qtd_necessaria:
        agrupados = {}
        for e in etapas:
            for item in e.get("escolhidos", []):
                nome = item.get("nome")
                agrupados[nome] = agrupados.get(nome, 0) + 1

        descricao_itens = "\n".join(
            [f"{qtd}x {nome}" for nome, qtd in agrupados.items()]
        )
        agrupados_internos = {}

        for e in etapas:
            for item in e.get("escolhidos", []):
                item_id = item.get("id")
                if item_id not in agrupados_internos:
                    agrupados_internos[item_id] = {
                        "id": item_id,
                        "nome": item.get("nome"),
                        "qtd": 0,
                    }
                agrupados_internos[item_id]["qtd"] += 1

        itens_internos = list(agrupados_internos.values())

        carrinho.append(
            {
                "id": combo.get("id_combo"),
                "indice": combo.get("indice"),
                "qtd": 1,
                "nome": combo.get("nome"),
                "precoUnitario": float(combo.get("preco", 0)),
                "itens_internos": itens_internos,
            }
        )

        sql_update = f"UPDATE conversas_bot SET carrinho_json = '{json.dumps(carrinho)}'::jsonb, combo_em_montagem = NULL, item_pendente_combo = NULL, estado_conversa = 'visualizando_carrinho', ultima_interacao = NOW() WHERE jid = '{user_id}';"
        mensagem_resposta = (
            f"Combo montado! 🎉\n\n*{combo.get('nome')}:*\n\n{descricao_itens}\n"
        )

        return {
            "sql_update": sql_update,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real or user_id,
                "type": "text",
                "text": {
                    "body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n{mensagem_resposta}"
                },
            },
        }

    limite_sabor_atingido = False
    if limite_sabor != float("inf"):
        total_mesmo_item = sum(
            1 for i in etapa["escolhidos"] if i.get("id") == item_pendente.get("id")
        )
        limite_sabor_atingido = total_mesmo_item >= limite_sabor

    if limite_sabor_atingido and len(etapas) > 1:
        combo["etapaAtual"] += 1
        if combo["etapaAtual"] >= len(etapas):
            combo["etapaAtual"] = len(etapas) - 1

    categoria_atual = etapas[combo["etapaAtual"]].get("categoria")
    sql_update = f"UPDATE conversas_bot SET combo_em_montagem = '{json.dumps(combo)}'::jsonb, item_pendente_combo = NULL, estado_conversa = 'montando_combo', ultima_interacao = NOW() WHERE jid = '{user_id}';"
    mensagem_resposta = (
        f"Adicionado!\nFaltam {qtd_necessaria - total_escolhidos_geral} item(ns)."
    )

    return {
        "buscar_novo_menu": True,
        "proxima_categoria": categoria_atual,
        "sql_update": sql_update,
        "payload": {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real or user_id,
            "type": "text",
            "text": {"body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n{mensagem_resposta}"},
        },
    }
