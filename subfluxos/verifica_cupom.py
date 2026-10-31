import json
import logging
import uuid

logger = logging.getLogger(__name__)


async def processar_verificacao_cupom(
    user_id: str,
    telefone_real: str,
    primeiro_nome: str,
    mensagem_cliente: str,
    dados_estado: dict,
    dados_cupom_notion: dict = None,
) -> dict:
    cupom_digitado = str(mensagem_cliente).strip()
    cupom_cadastrado = str(dados_estado.get("cupom", "")).strip()

    dados_cupom_notion = dados_cupom_notion or {}
    property_cupom = str(dados_cupom_notion.get("Cupom", "")).strip()

    is_validade = not bool(cupom_cadastrado) and not bool(property_cupom)

    if is_validade:
        sql_update = f"UPDATE conversas_bot SET estado_conversa = 'visualizando_carrinho', expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{user_id}';"
        msg_expirado = f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_{primeiro_nome}_,\nInfelizmente o código *{cupom_digitado}* \nperdeu a validade e você\nnão possui mais nenhum\ncupom de desconto ❌\n\nAguarde... ⌛"
        return {
            "sql_update": sql_update,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "text",
                "text": {"body": msg_expirado},
            },
        }

    is_correto = (
        cupom_digitado.lower() == cupom_cadastrado.lower() and bool(cupom_cadastrado)
    ) or (cupom_digitado.upper() == property_cupom.upper() and bool(property_cupom))

    if not is_correto:
        sql_update = f"UPDATE conversas_bot SET estado_conversa = 'tenta_cupom', expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{user_id}';"
        return {
            "sql_update": sql_update,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {
                        "text": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\nO código digitado *{cupom_digitado}* é inválido ❌\n\nComo deseja seguir? 🤔\n​"
                    },
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {"id": "1", "title": "🔁 Tentar Novamente"},
                            },
                            {
                                "type": "reply",
                                "reply": {"id": "2", "title": "⭕ Comprar Sem Cupom"},
                            },
                        ]
                    },
                },
            },
        }

    valor_pedido = float(dados_estado.get("valor_pedido", 0))
    valor_minimo = float(
        dados_estado.get("valor_minimo_cupom")
        or dados_cupom_notion.get("Pedido Mínimo", 0)
    )

    atinge_minimo = valor_pedido >= valor_minimo
    valor_faltante = 0.0 if atinge_minimo else (valor_minimo - valor_pedido)
    valor_faltante_fmt = (
        f"R$ {valor_faltante:,.2f}".replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )

    if not atinge_minimo:
        sql_update = f"UPDATE conversas_bot SET estado_conversa = 'adiciona_itens_cupom', expirando = FALSE, is_bot_paused = FALSE, cupom_promo = '{cupom_digitado}', ultima_interacao = NOW() WHERE jid = '{user_id}';"
        return {
            "sql_update": sql_update,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {
                        "text": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\nEste *CUPOM* é válido\napenas para compras\nacima de *R$ {valor_minimo:,.2f}*\n\n→ O valor do seu pedido é:\n*R$ {valor_pedido:,.2f}*\n\n→ Para ativar o cupom faltam:\n*{valor_faltante_fmt}*\n\nComo deseja seguir? 🤔\n​"
                    },
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {"id": "1", "title": "➕ Adicionar Itens"},
                            },
                            {
                                "type": "reply",
                                "reply": {"id": "2", "title": "✅ Finalizar Pedido"},
                            },
                            {"type": "reply", "reply": {"id": "3", "title": "❌ Sair"}},
                        ]
                    },
                },
            },
        }

    carrinho_raw = dados_estado.get("carrinho_json", "[]")
    try:
        carrinho = (
            json.loads(carrinho_raw) if isinstance(carrinho_raw, str) else carrinho_raw
        )
    except Exception:
        carrinho = []

    total_geral = 0.0
    carrinho_texto = ""

    for item in carrinho:
        qtd = int(item.get("qtd", 0))
        preco_unitario = float(item.get("precoUnitario", 0))
        subtotal = qtd * preco_unitario
        total_geral += subtotal

        preco_fmt = (
            f"R$ {preco_unitario:,.2f}".replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )
        subtotal_fmt = (
            f"R$ {subtotal:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        indice = item.get("indice", item.get("Indice", "?"))
        nome_item = item.get("nome", "").strip()

        carrinho_texto += f"*{indice})* {'📦' if 'combo' in nome_item.lower() else '🍫'} {nome_item}\n\n*Quantidade:* {qtd}\n*Preço:* {preco_fmt} *({subtotal_fmt})*\n"

        itens_internos = item.get("itens_internos", [])
        if itens_internos:
            carrinho_texto += "*Itens do Combo:*\n"
            for sub_item in itens_internos:
                carrinho_texto += (
                    f"{sub_item.get('qtd', 1)}x {sub_item.get('nome', '')}\n"
                )
            carrinho_texto += "\n\n"

        carrinho_texto += "--------------------------------------------------\n\n"

    percentual_desconto = float(
        dados_estado.get("desconto", dados_cupom_notion.get("Desconto", 0))
    )
    limite_desconto = float(dados_cupom_notion.get("Limite", 0) or 0)

    valor_desconto = 0.0
    total_com_desconto = total_geral
    texto_desconto = ""

    if percentual_desconto > 0:
        desconto_calculado = total_geral * (percentual_desconto / 100)
        valor_desconto = (
            limite_desconto
            if limite_desconto > 0 and desconto_calculado > limite_desconto
            else desconto_calculado
        )
        total_com_desconto = max(0, total_geral - valor_desconto)
        desc_fmt = (
            f"R$ {valor_desconto:,.2f}".replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )
        texto_desconto = f"*💸→ DESCONTO:*\n_*-{desc_fmt}*_\n\n"

    t_geral_fmt = (
        f"R$ {total_geral:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )
    t_desc_fmt = (
        f"R$ {total_com_desconto:,.2f}".replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )

    mensagem_pedido = f"*🛍️→ PEDIDO:*\n\n{carrinho_texto}"
    if valor_desconto > 0:
        mensagem_pedido += texto_desconto
    mensagem_pedido += (
        f"*🪙→ VALOR PEDIDO:*\n~{t_geral_fmt}~ *{t_desc_fmt}*\n\n"
        if valor_desconto > 0
        else f"*🪙→ VALOR PEDIDO:*\n*{t_geral_fmt}*\n\n"
    )

    endereco = dados_estado.get("endereco")

    if not endereco:
        sql_update = f"UPDATE conversas_bot SET estado_conversa = 'cadastra_endereco', print_carrinho = '{mensagem_pedido}', valor_pedido = '{total_com_desconto:.2f}', cupom_promo = '{cupom_digitado}', expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{user_id}';"
        flow_token = str(uuid.uuid4())
        return {
            "sql_update": sql_update,
            "mensagens_multiplas": [
                {"type": "text", "text": {"body": f"{mensagem_pedido}\nㅤ"}},
                {
                    "type": "interactive",
                    "interactive": {
                        "type": "flow",
                        "body": {
                            "text": "_*👸🏾 Kakaw - TheLordTrufas.*_\n\nVou precisar de algumas\ninformações para calcular\no valor do _*FRETE*_ 🛵\n"
                        },
                        "action": {
                            "name": "flow",
                            "parameters": {
                                "flow_message_version": "3",
                                "flow_token": flow_token,
                                "flow_id": "1061262525861471",
                                "flow_cta": "Cadastrar Endereço",
                            },
                        },
                    },
                },
            ],
        }

    bairro = dados_estado.get("bairro", "")
    cep = dados_estado.get("cep", dados_estado.get("CEP", ""))
    cep_fmt = f"{cep[:5]}-{cep[5:]}" if len(cep) == 8 else cep
    complemento = dados_estado.get("complemento", "")

    msg_confirmacao = f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_{primeiro_nome}_\naqui está seu pedido com *CUPOM* aplicado:\n\n{mensagem_pedido}----------------------------------------------------------\n\nAgora para seguirmos,\nconfirme seu endereço: 🗺️\n\n*📍→ RUA/Nº:*\n\n{endereco}\n\n*📍→ BAIRRO:*\n\n{bairro}\n\n*📍→ CEP:*\n\n{cep_fmt}\n"
    if complemento:
        msg_confirmacao += f"\n*📍→ COMPLEMENTO:*\n\n\n{complemento}\n"

    sql_update = f"UPDATE conversas_bot SET estado_conversa = 'finalizando_pedido', print_carrinho = '{mensagem_pedido}', valor_pedido = '{total_com_desconto:.2f}', cupom_promo = '{cupom_digitado}', expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{user_id}';"

    return {
        "sql_update": sql_update,
        "mensagens_multiplas": [
            {"type": "text", "text": {"body": f"{msg_confirmacao}\nㅤ"}},
            {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": "Os dados do *endereço* acima estão corretos?\n"},
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {"id": "1", "title": "📍✅ Correto"},
                            },
                            {
                                "type": "reply",
                                "reply": {"id": "2", "title": "📍❌ Errado"},
                            },
                        ]
                    },
                },
            },
        ],
    }
