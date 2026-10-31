import json
import uuid


async def processar_visualizacao_carrinho(
    user_id, telefone_real, primeiro_nome, opcao_escolhida, dados_estado
):
    opcao = str(opcao_escolhida).strip()

    if opcao == "1":
        sql_update = f"UPDATE conversas_bot SET estado_conversa = 'aguardando_escolha_item', expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{user_id}';"
        return {
            "sql_update": sql_update,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "text",
                "text": {
                    "body": "_*👸🏾 Kakaw - TheLordTrufas.*_\n\nAdicione um novo item à sacola. ➕🛍️\n\nPara escolher é muito simples,\nbasta enviar o *NÚMERO*\nreferente ao *ITEM*\nno *CARDÁPIO*.\nㅤ"
                },
            },
        }

    elif opcao == "2":
        carrinho_raw = dados_estado.get("carrinho_json", "[]")
        try:
            carrinho_array = (
                json.loads(carrinho_raw)
                if isinstance(carrinho_raw, str)
                else carrinho_raw
            )
        except Exception:
            carrinho_array = []

        carrinho_texto = ""
        for item in carrinho_array:
            indice = item.get("indice", "?")
            nome_item = item.get("nome", "Item").strip()
            qtd = int(item.get("qtd", 0))
            preco_unitario = float(item.get("precoUnitario", item.get("preco", 0.0)))
            subtotal = qtd * preco_unitario

            preco_fmt = (
                f"R$ {preco_unitario:,.2f}".replace(",", "X")
                .replace(".", ",")
                .replace("X", ".")
            )
            subtotal_fmt = (
                f"R$ {subtotal:,.2f}".replace(",", "X")
                .replace(".", ",")
                .replace("X", ".")
            )

            carrinho_texto += f"*{indice})* {'📦' if 'combo' in nome_item.lower() else '🍫'} {nome_item}\n\n*Quantidade:* {qtd}\n*Preço:* {preco_fmt} *({subtotal_fmt})*\n"

            itens_internos = item.get("itens_internos", [])
            if itens_internos:
                carrinho_texto += "*Itens do Combo:*\n"
                for sub in itens_internos:
                    carrinho_texto += f"{sub.get('qtd')}x {sub.get('nome')}\n"
                carrinho_texto += "\n\n"
            carrinho_texto += (
                "----------------------------------------------------------\n\n"
            )

        if not carrinho_texto:
            carrinho_texto = "O seu carrinho está vazio."

        sql_update = f"UPDATE conversas_bot SET estado_conversa = 'aguardando_alteracao_item', expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{user_id}';"
        return {
            "sql_update": sql_update,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "text",
                "text": {
                    "body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_*{primeiro_nome}*_,\nnessa etapa você pode\n*ALTERAR* e *REMOVER* itens\nque talvez tenha escolhido\nerrado. ✍️🛒\n\n{carrinho_texto}É muito simples,\nbasta enviar o *NÚMERO*\nreferente ao *ITEM*\nna *LISTA* acima.\nㅤ"
                },
            },
        }

    elif opcao == "3":
        if not dados_estado.get("cupom_promo", ""):
            sql_update = f"UPDATE conversas_bot SET estado_conversa = 'existe_cupom', expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{user_id}';"
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
                            "text": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_*{primeiro_nome}*_,\nvocê possui algum *cupom de desconto*\npara aplicar no seu pedido? 🎟️\n"
                        },
                        "action": {
                            "buttons": [
                                {
                                    "type": "reply",
                                    "reply": {"id": "1", "title": "👍 Tenho Cupom"},
                                },
                                {
                                    "type": "reply",
                                    "reply": {
                                        "id": "2",
                                        "title": "👎 Não Possuo Cupom",
                                    },
                                },
                            ]
                        },
                    },
                },
            }
        else:
            return {
                "acionar_fluxo_interno": True,
                "proximo_estado": "verificar_cupom_novamente",
            }

    elif opcao == "4":
        return {"acionar_fluxo_interno": True, "proximo_estado": "menu_inicio"}

    elif opcao == "5":
        from subfluxos.gerenciador_encerramento import processar_encerramento_sessao

        return await processar_encerramento_sessao(
            user_id,
            telefone_real,
            primeiro_nome,
            dados_estado.get("carrinho_json", "[]"),
            "sair",
        )

    elif opcao == "6":
        endereco = dados_estado.get("endereco", "")
        bairro = dados_estado.get("bairro", "")
        cep = dados_estado.get("CEP", "")
        complemento = dados_estado.get("complemento", "")
        mensagem_resposta_carrinho = dados_estado.get(
            "print_carrinho", "Resumo Indisponível\n"
        )

        if not endereco:
            sql_update = f"UPDATE conversas_bot SET estado_conversa = 'cadastra_endereco', expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{user_id}';"
            flow_token = uuid.uuid4().hex
            return {
                "sql_update": sql_update,
                "payload": {
                    "messaging_product": "whatsapp",
                    "to": telefone_real,
                    "recipient_type": "individual",
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
            }

        cep_fmt = f"{cep[:5]}-{cep[5:]}" if len(cep) >= 8 else cep
        verifica_endereco = f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_*{primeiro_nome}*_ \naqui está seu pedido:\n\n{mensagem_resposta_carrinho}----------------------------------------------------------\n\nAgora para seguirmos,\nconfirme seu endereço: 🗺️\n\n*📍→ RUA/Nº:*\n\n{endereco}\n\n*📍→ BAIRRO:*\n\n{bairro}\n\n*📍→ CEP:*\n\n{cep_fmt}\n"
        if complemento:
            verifica_endereco += f"\n*📍→ COMPLEMENTO:*\n\n\n{complemento}\n"

        sql_update = f"UPDATE conversas_bot SET estado_conversa = 'finalizando_pedido', expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{user_id}';"

        return {
            "sql_update": sql_update,
            "mensagens_multiplas": [
                {"type": "text", "text": {"body": f"{verifica_endereco}\nㅤ"}},
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

    return {
        "sql_update": None,
        "payload": {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {
                    "text": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_*{primeiro_nome}*_, sua mensagem\nnão é válida. Por favor escolha\numa das opções abaixo:\n"
                },
                "footer": {
                    "text": "Clique no botão abaixo e escolha a opção desejada."
                },
                "action": {
                    "button": "VER OPÇÕES",
                    "sections": [
                        {
                            "title": "Opções Principais",
                            "rows": [
                                {"id": "1", "title": "➕ Adicionar Mais"},
                                {
                                    "id": "2",
                                    "title": "✍️🗑️ Alterar/Remover",
                                    "description": "Altere a quantidade ou remova um item do carrinho",
                                },
                                {"id": "3", "title": "✅ Finalizar Pedido"},
                                {"id": "4", "title": "⏮️ Menu Principal"},
                                {"id": "5", "title": "❌ Sair"},
                            ],
                        }
                    ],
                },
            },
        },
    }
