import json
import logging

logger = logging.getLogger(__name__)


async def processar_calculo_pedido(
    user_id: str, telefone_real: str, primeiro_nome: str, dados_estado: dict
) -> dict:
    logger.info(f"🧮 Calculando Pedido | JID: {user_id}")

    carrinho_raw = dados_estado.get("carrinho_json")
    try:
        carrinho_array = (
            json.loads(carrinho_raw) if isinstance(carrinho_raw, str) else carrinho_raw
        )
    except Exception:
        carrinho_array = []

    # =========================================================
    # CORREÇÃO: Menu de Categorias Direto ao Esvaziar Sacola
    # =========================================================
    if not isinstance(carrinho_array, list) or len(carrinho_array) == 0:
        sql_vazio = f"UPDATE conversas_bot SET estado_conversa = 'aguardando_categoria', expirando = FALSE, valor_pedido = '0.00', item_selecionado_id = NULL, ultima_interacao = NOW() WHERE jid = '{user_id}';"

        payload_botoes_vazio = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_*{primeiro_nome}*_, \n*Sua Sacola está vazia.* 🛒\n\nEscolha uma categoria para visualizar os itens disponíveis:\n"
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "1",
                                "title": "🍫 Individuais",
                            },
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "2",
                                "title": "📦 Combos",
                            },
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "3",
                                "title": "⏮️ Menu Principal",
                            },
                        },
                    ]
                },
            },
        }

        return {
            "sql_update": sql_vazio,
            "payload": payload_botoes_vazio,
        }

    total_geral = 0.0
    carrinho_texto = ""

    for item in carrinho_array:
        qtd = int(item.get("qtd", 0))
        preco_unitario = float(item.get("precoUnitario", item.get("preco", 0.0)))
        subtotal = qtd * preco_unitario
        total_geral += subtotal
        indice = str(item.get("indice", "?"))
        nome_item = item.get("nome", "Item").strip()

        carrinho_texto += (
            f"*{indice})* 📦 {nome_item}\n\n"
            if "combo" in nome_item.lower()
            else f"*{indice})* 🍫 {nome_item}\n\n"
        )
        preco_fmt = (
            f"R$ {preco_unitario:,.2f}".replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )
        subtotal_fmt = (
            f"R$ {subtotal:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        carrinho_texto += (
            f"*Quantidade:* {qtd}\n*Preço:* {preco_fmt} *({subtotal_fmt})*\n\n"
        )

        if itens_internos := item.get("itens_internos", []):
            carrinho_texto += "*Itens do Combo:*\n"
            for sub in itens_internos:
                carrinho_texto += f"{sub.get('qtd')}x {sub.get('nome')}\n"
            carrinho_texto += "\n"
        carrinho_texto += (
            "\n----------------------------------------------------------\n\n"
        )

    total_formatado = (
        f"R${total_geral:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )
    print_carrinho = f"*🛍️→ PEDIDO:*\n\n{carrinho_texto}*🪙→ VALOR PEDIDO:*\n*{total_formatado}*\n\u200b"

    VALOR_MINIMO_FRETE = 45.00
    frete_atingiu_minimo = total_geral >= VALOR_MINIMO_FRETE
    valor_faltante_fmt = (
        f"R$ {max(0.0, VALOR_MINIMO_FRETE - total_geral):,.2f}".replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )

    frete_msg = (
        "✨ Parabéns você atingiu o valor mínimo para ter *DESCONTO TOTAL* ou *PARCIAL* no seu *FRETE*! 🛵"
        if frete_atingiu_minimo
        else f"⚠️ Atenção: Faltam *{valor_faltante_fmt}* para você ter *DESCONTO TOTAL* ou *PARCIAL* no seu *FRETE*! 🛵"
    )
    mensagem_resposta = f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_*{primeiro_nome}*_,\nconfira seu pedido:\n\n{print_carrinho}\n"

    sql_atualizacao = f"UPDATE conversas_bot SET estado_conversa = 'visualizando_carrinho', expirando = FALSE, valor_pedido = '{total_geral:.2f}', print_carrinho = '{print_carrinho}', item_selecionado_id = NULL, ultima_interacao = NOW() WHERE jid = '{user_id}';"

    payload_menu = {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\nComo deseja seguir com o atendimento?\n"
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "1",
                            "title": "➕ Adicionar Mais",
                        },
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "2",
                            "title": "✍️🗑️ Alterar/Remover",
                        },
                    },
                    {
                        "type": "reply",
                        "reply": {"id": "3", "title": "✅ Finalizar Pedido"},
                    },
                ]
            },
        },
    }

    return {
        "sql_update": sql_atualizacao,
        "mensagens_multiplas": [
            {"type": "text", "text": {"body": mensagem_resposta}},
            payload_menu,
        ],
    }
