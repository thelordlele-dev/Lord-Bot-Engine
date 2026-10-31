import json
import uuid


async def processar_existe_cupom(
    user_id, telefone_real, primeiro_nome, mensagem_cliente, dados_estado
):
    """
    [MÓDULO 1.16 - Existe Cupom / 1.17 - Nova Tentativa Cupom]
    Gerencia a decisão sobre inserção de cupom ou seguimento do pedido,
    avaliando regras de frete mínimo e estado do endereço do cliente.
    """
    opcao = str(mensagem_cliente).strip()

    # -------------------------------------------------------------
    # CASO 1: Cliente quer inserir cupom (Opção "1")
    # -------------------------------------------------------------
    if opcao == "1":
        sql_update = f"""
            UPDATE conversas_bot 
            SET estado_conversa = 'verifica_cupom', 
                expirando = FALSE, 
                ultima_interacao = NOW() 
            WHERE jid = '{user_id}'
        """
        return {
            "proximo_estado": "verifica_cupom",
            "sql_update": sql_update.strip(),
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "text",
                "text": {
                    "body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_{primeiro_nome}_,\npor favor digite o\n*CÓDIGO DO CUPOM*:"
                },
            },
        }

    # -------------------------------------------------------------
    # CASO 2: Cliente segue SEM cupom (Processamento do Carrinho)
    # -------------------------------------------------------------
    carrinho_raw = dados_estado.get("carrinho_json", "[]")
    try:
        carrinho = (
            json.loads(carrinho_raw) if isinstance(carrinho_raw, str) else carrinho_raw
        )
    except Exception:
        carrinho = []

    if not carrinho or not isinstance(carrinho, list):
        return {"erro": "Carrinho vazio ou inválido."}

    total_geral = 0.0
    carrinho_texto = ""

    for item in carrinho:
        qtd = int(item.get("qtd", 0))
        preco_unitario = float(item.get("precoUnitario", 0))
        subtotal = qtd * preco_unitario
        total_geral += subtotal

        # Formatação monetária PT-BR
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

        carrinho_texto += f"*{indice})* "
        if "combo" in nome_item.lower():
            carrinho_texto += f"📦 {nome_item}\n\n"
        else:
            carrinho_texto += f"🍫 {nome_item}\n\n"

        carrinho_texto += f"*Quantidade:* {qtd}\n"
        carrinho_texto += f"*Preço:* {preco_fmt} *({subtotal_fmt})*\n"

        # Itens internos do combo (se houver)
        itens_internos = item.get("itens_internos", [])
        if itens_internos:
            carrinho_texto += "*Itens do Combo:*\n"
            for sub_item in itens_internos:
                carrinho_texto += (
                    f"{sub_item.get('qtd', 1)}x {sub_item.get('nome', '')}\n"
                )
            carrinho_texto += "\n\n"

        carrinho_texto += "--------------------------------------------------\n\n"

    # Regra de Frete Mínimo (R$ 45,00)
    VALOR_MINIMO_FRETE = 45.00
    frete_atingiu_minimo = total_geral >= VALOR_MINIMO_FRETE
    valor_faltante = max(0, VALOR_MINIMO_FRETE - total_geral)

    total_fmt = (
        f"R$ {total_geral:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )
    faltante_fmt = (
        f"R$ {valor_faltante:,.2f}".replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )

    mensagem_pedido = (
        f"*🛍️→ PEDIDO:*\n\n"
        f"{carrinho_texto}"
        f"*🪙→ VALOR PEDIDO:*\n"
        f"*{total_fmt}*\n\n"
    )

    # -------------------------------------------------------------
    # SUB-FLUXO A: Frete Mínimo NÃO Atingido
    # -------------------------------------------------------------
    if not frete_atingiu_minimo:
        frete_full_msg = f"⚠️ Atenção: Faltam *{faltante_fmt}* para você ter *DESCONTO TOTAL* ou *PARCIAL* no seu *FRETE*! 🛵"

        sql_update = f"""
            UPDATE conversas_bot 
            SET estado_conversa = 'adiciona_itens_frete', 
                expirando = FALSE, 
                is_bot_paused = FALSE, 
                ultima_interacao = NOW() 
            WHERE jid = '{user_id}'
        """

        return {
            "proximo_estado": "adiciona_itens_frete",
            "sql_update": sql_update.strip(),
            "mensagens_multiplas": [
                {
                    "type": "text",
                    "text": {
                        "body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_{primeiro_nome}_,\nconfira seu pedido:\n\n{mensagem_pedido}\n{frete_full_msg}\nㅤ"
                    },
                },
                {
                    "type": "interactive",
                    "interactive": {
                        "type": "button",
                        "body": {
                            "text": "_*👸🏾 Kakaw - TheLordTrufas.*_\n\nComo deseja seguir com o atendimento?\n"
                        },
                        "action": {
                            "buttons": [
                                {
                                    "type": "reply",
                                    "reply": {"id": "1", "title": "➕ Adicionar Itens"},
                                },
                                {
                                    "type": "reply",
                                    "reply": {
                                        "id": "2",
                                        "title": "✅ Finalizar Pedido",
                                    },
                                },
                                {
                                    "type": "reply",
                                    "reply": {"id": "3", "title": "❌ Sair"},
                                },
                            ]
                        },
                    },
                },
            ],
        }

    # -------------------------------------------------------------
    # SUB-FLUXO B: Frete Mínimo Atingido
    # -------------------------------------------------------------
    frete_desconto_msg = "✨ Parabéns você atingiu o valor mínimo para ter *DESCONTO TOTAL* ou *PARCIAL* no seu *FRETE*! 🛵"
    endereco = dados_estado.get("endereco")

    # B.1: Cliente ainda não tem endereço cadastrado (Dispara WhatsApp Flow)
    if not endereco:
        sql_update = f"""
            UPDATE conversas_bot 
            SET estado_conversa = 'cadastra_endereco', 
                print_carrinho = '{mensagem_pedido}', 
                valor_pedido = '{total_geral:.2f}', 
                expirando = FALSE, 
                ultima_interacao = NOW() 
            WHERE jid = '{user_id}'
        """
        flow_token = str(uuid.uuid4())

        return {
            "proximo_estado": "cadastra_endereco",
            "sql_update": sql_update.strip(),
            "mensagens_multiplas": [
                {
                    "type": "text",
                    "text": {"body": f"{mensagem_pedido}\n{frete_desconto_msg}\n"},
                },
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

    # B.2: Cliente já possui endereço cadastrado (Confirmação)
    bairro = dados_estado.get("bairro", "")
    cep = dados_estado.get("cep", dados_estado.get("CEP", ""))
    cep_fmt = f"{cep[:5]}-{cep[5:]}" if len(cep) == 8 else cep
    complemento = dados_estado.get("complemento", "")

    msg_confirmacao = (
        f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_{primeiro_nome}_\n"
        f"aqui está seu pedido:\n\n{mensagem_pedido}"
        f"----------------------------------------------------------\n\n"
        f"Agora para seguirmos,\nconfirme seu endereço: 🗺️\n\n"
        f"*📍→ RUA/Nº:*\n\n{endereco}\n\n"
        f"*📍→ BAIRRO:*\n\n{bairro}\n\n"
        f"*📍→ CEP:*\n\n{cep_fmt}\n"
    )
    if complemento:
        msg_confirmacao += f"\n*📍→ COMPLEMENTO:*\n\n\n{complemento}\n"
    else:
        msg_confirmacao += ""

    sql_update = f"""
        UPDATE conversas_bot 
        SET estado_conversa = 'finalizando_pedido', 
            print_carrinho = '{mensagem_pedido}', 
            valor_pedido = '{total_geral:.2f}', 
            expirando = FALSE, 
            ultima_interacao = NOW() 
        WHERE jid = '{user_id}'
    """

    return {
        "proximo_estado": "finalizando_pedido",
        "sql_update": sql_update.strip(),
        "mensagens_multiplas": [
            {
                "type": "text",
                "text": {"body": f"{msg_confirmacao}\n\n{frete_desconto_msg}\nㅤ"},
            },
            {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {
                        "text": "Os dados do *endereço* acima estão corretos?\n"
                    },
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
