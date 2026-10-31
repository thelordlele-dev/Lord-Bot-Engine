import json
import logging

logger = logging.getLogger(__name__)


async def processar_montagem_combo(
    user_id: str,
    telefone_real: str,
    primeiro_nome: str,
    mensagem_cliente: str,
    combo_em_montagem_str: str,
    mapa_id_json_str: str,
) -> dict:
    try:
        combo = (
            json.loads(combo_em_montagem_str)
            if isinstance(combo_em_montagem_str, str)
            else combo_em_montagem_str
        )
        mapa_id = (
            json.loads(mapa_id_json_str)
            if isinstance(mapa_id_json_str, str)
            else mapa_id_json_str
        )
    except Exception:
        sql_erro = f"UPDATE conversas_bot SET estado_conversa = 'menu_inicio', combo_em_montagem = NULL, ultima_interacao = NOW() WHERE jid = '{user_id}';"
        return {
            "sql_update": sql_erro,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "text",
                "text": {
                    "body": "_*👸🏾 Kakaw - TheLordTrufas.*_\n\nErro técnico ao processar o combo. Reiniciando atendimento."
                },
            },
        }

    opcao = str(mensagem_cliente).strip()
    item_escolhido = mapa_id.get(opcao)

    if not item_escolhido:
        return {
            "sql_update": None,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "text",
                "text": {
                    "body": "_*👸🏾 Kakaw - TheLordTrufas.*_\n\nOpção inválida. Por favor, escolha um número válido do cardápio."
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
                "to": telefone_real,
                "type": "text",
                "text": {
                    "body": "_*👸🏾 Kakaw - TheLordTrufas.*_\n\nErro na montagem do combo. Etapa não encontrada."
                },
            },
        }

    etapa_atual = etapas[etapa_atual_idx]
    escolhidos = etapa_atual.get("escolhidos", [])
    faltam_na_etapa = int(etapa_atual.get("quantidade", 1)) - len(escolhidos)

    limite_regra = float("inf")
    regra = etapa_atual.get("regra", "")

    if regra and "_por_sabor" in regra:
        try:
            limite_por_sabor = int(regra.split("_")[0])
            ja_tem = sum(
                1 for i in escolhidos if i.get("id") == item_escolhido.get("id")
            )
            limite_regra = limite_por_sabor - ja_tem
        except Exception:
            pass

    estoque = int(item_escolhido.get("estq", 0))
    ja_no_combo = sum(1 for i in escolhidos if i.get("id") == item_escolhido.get("id"))
    estoque_disponivel = estoque - ja_no_combo
    maximo_permitido = min(faltam_na_etapa, limite_regra, estoque_disponivel)

    if maximo_permitido <= 0:
        return {
            "sql_update": None,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "text",
                "text": {
                    "body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n⚠️ Limite atingido para *{item_escolhido.get('nome')}*."
                },
            },
        }

    item_pendente = {
        "id": item_escolhido.get("id"),
        "nome": item_escolhido.get("nome"),
        "preco": item_escolhido.get("preco"),
        "max_qtd": maximo_permitido,
    }
    aviso_extra = (
        "\n_(Quantidade máxima 1)_"
        if maximo_permitido == 1
        else f"\n_(Quantidade máxima {maximo_permitido})_"
    )
    mensagem_resposta = f"_*👸🏾 Kakaw - TheLordTrufas*_\n\nQuantas unidades de *{item_escolhido.get('nome')}*?{aviso_extra}"

    sql_update = f"UPDATE conversas_bot SET estado_conversa = 'montando_combo_qtd', item_pendente_combo = '{json.dumps(item_pendente)}'::jsonb, ultima_interacao = NOW() WHERE jid = '{user_id}';"

    return {
        "sql_update": sql_update,
        "payload": {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real,
            "type": "text",
            "text": {"body": mensagem_resposta},
        },
    }
