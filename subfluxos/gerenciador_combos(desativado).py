import json


async def processar_montagem_combo(dados_estado: dict, mensagem_cliente: str) -> dict:
    jid = dados_estado.get("jid")
    telefone_real = dados_estado.get("telefone_real", jid)
    etapa_atual_fluxo = dados_estado.get("estado_conversa")
    usa_cupom = dados_estado.get("usa_cupom", False)

    try:
        combo = dados_estado.get("combo_em_montagem")
        if isinstance(combo, str):
            combo = json.loads(combo)

        mapa_id = dados_estado.get("mapa_id_json")
        if isinstance(mapa_id, str):
            mapa_id = json.loads(mapa_id)

        carrinho = dados_estado.get("carrinho_json")
        if isinstance(carrinho, str):
            carrinho = json.loads(carrinho)
        if not isinstance(carrinho, list):
            carrinho = []

        item_pendente = dados_estado.get("item_pendente_combo")
        if isinstance(item_pendente, str):
            item_pendente = json.loads(item_pendente) if item_pendente else {}

    except Exception:
        return {
            "sql_update": f"UPDATE conversas_bot SET estado_conversa='menu_inicio', combo_em_montagem=NULL, item_pendente_combo=NULL WHERE jid='{jid}';",
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "text",
                "text": {
                    "body": "⚠️ Ocorreu um erro técnico na montagem do seu combo. Vamos reiniciar."
                },
            },
        }

    if etapa_atual_fluxo == "montando_combo_item":
        mensagem_limpa = mensagem_cliente.strip()
        item_escolhido = mapa_id.get(mensagem_limpa)

        if not item_escolhido:
            prefixo_erro = "⚠️ *Cupom Inválido/Erro:* " if usa_cupom else "⚠️ "
            return {
                "sql_update": None,
                "payload": {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": telefone_real,
                    "type": "text",
                    "text": {
                        "body": f"{prefixo_erro}Opção inválida. Por favor, escolha um número válido do cardápio."
                    },
                },
            }

        etapa_combo_atual = combo.get("etapas", [])[combo.get("etapaAtual", 0)]
        escolhidos_etapa = etapa_combo_atual.get("escolhidos", [])
        faltam_na_etapa = (etapa_combo_atual.get("quantidade", 1)) - len(
            escolhidos_etapa
        )

        limite_regra = float("inf")
        regra_etapa = etapa_combo_atual.get("regra", "")
        if "_por_sabor" in regra_etapa:
            limite_por_sabor = int(regra_etapa.split("_")[0])
            ja_tem_sabor = sum(
                1 for i in escolhidos_etapa if i.get("id") == item_escolhido.get("id")
            )
            limite_regra = limite_por_sabor - ja_tem_sabor

        estoque = int(item_escolhido.get("estq", 0))
        ja_no_combo = sum(
            1 for i in escolhidos_etapa if i.get("id") == item_escolhido.get("id")
        )
        estoque_disponivel = estoque - ja_no_combo

        maximo_permitido = min(faltam_na_etapa, limite_regra, estoque_disponivel)

        novo_item_pendente = {
            "id": item_escolhido.get("id"),
            "nome": item_escolhido.get("nome"),
            "preco": item_escolhido.get("preco"),
            "max_qtd": maximo_permitido,
        }

        aviso_max = (
            f"\n_(Quantidade máxima: {maximo_permitido})_"
            if maximo_permitido > 0
            else ""
        )
        sql_atualizacao = f"UPDATE conversas_bot SET estado_conversa = 'montando_combo_qtd', item_pendente_combo = '{json.dumps(novo_item_pendente)}'::jsonb, ultima_interacao = NOW() WHERE jid = '{jid}';"

        return {
            "sql_update": sql_atualizacao,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "text",
                "text": {
                    "body": f"Quantas unidades de *{item_escolhido.get('nome')}*?{aviso_max}"
                },
            },
        }

    elif etapa_atual_fluxo == "montando_combo_qtd":
        try:
            quantidade_digitada = int(mensagem_cliente.strip())
        except ValueError:
            return {
                "sql_update": None,
                "payload": {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": telefone_real,
                    "type": "text",
                    "text": {
                        "body": "⚠️ Por favor, digite apenas um número válido para a quantidade."
                    },
                },
            }

        if quantidade_digitada <= 0:
            return {
                "sql_update": None,
                "payload": {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": telefone_real,
                    "type": "text",
                    "text": {"body": "⚠️ A quantidade deve ser maior do que zero."},
                },
            }

        etapa_combo_atual = combo.get("etapas", [])[combo.get("etapaAtual", 0)]
        if "escolhidos" not in etapa_combo_atual:
            etapa_combo_atual["escolhidos"] = []

        limite_sabor = float("inf")
        regra_etapa = etapa_combo_atual.get("regra", "")
        if "_por_sabor" in regra_etapa:
            limite_sabor = int(regra_etapa.split("_")[0])

        ja_tem_mesmo_sabor = sum(
            1
            for i in etapa_combo_atual["escolhidos"]
            if i.get("id") == item_pendente.get("id")
        )
        restante_sabor = limite_sabor - ja_tem_mesmo_sabor

        if ja_tem_mesmo_sabor + quantidade_digitada > limite_sabor:
            return {
                "sql_update": None,
                "payload": {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": telefone_real,
                    "type": "text",
                    "text": {
                        "body": f"⚠️ Você pode adicionar no máximo {restante_sabor} unidade(s) desse item ({item_pendente.get('nome')}). Envie novamente a quantidade:"
                    },
                },
            }

        total_atual_combo = sum(
            len(e.get("escolhidos", [])) for e in combo.get("etapas", [])
        )
        qtd_necessaria_combo = int(combo.get("qtd_necessaria", 0))
        restante_combo = qtd_necessaria_combo - total_atual_combo

        if total_atual_combo + quantidade_digitada > qtd_necessaria_combo:
            return {
                "sql_update": None,
                "payload": {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": telefone_real,
                    "type": "text",
                    "text": {
                        "body": f"⚠️ Você pode adicionar no máximo {restante_combo} unidade(s) no total para este combo. Envie novamente a quantidade:"
                    },
                },
            }

        for _ in range(quantidade_digitada):
            etapa_combo_atual["escolhidos"].append(
                {
                    "id": item_pendente.get("id"),
                    "nome": item_pendente.get("nome"),
                    "preco_original": item_pendente.get("preco"),
                }
            )

        total_escolhidos_geral = sum(
            len(e.get("escolhidos", [])) for e in combo.get("etapas", [])
        )

        if total_escolhidos_geral >= qtd_necessaria_combo:
            agrupados_internos = {}
            for estp in combo.get("etapas", []):
                for item in estp.get("escolhidos", []):
                    item_id = item.get("id")
                    if item_id not in agrupados_internos:
                        agrupados_internos[item_id] = {
                            "id": item_id,
                            "nome": item.get("nome"),
                            "qtd": 0,
                        }
                    agrupados_internos[item_id]["qtd"] += 1

            itens_internos_lista = list(agrupados_internos.values())
            preco_final_combo = (
                combo.get("preco_com_cupom")
                if (usa_cupom and combo.get("preco_com_cupom"))
                else combo.get("preco_normal")
            )

            carrinho.append(
                {
                    "id": combo.get("id_combo"),
                    "indice": combo.get("indice"),
                    "qtd": 1,
                    "nome": combo.get("nome"),
                    "preco": preco_final_combo,
                    "itens_internos": itens_internos_lista,
                    "com_cupom": usa_cupom,
                }
            )

            sql_finalizacao = f"UPDATE conversas_bot SET estado_conversa = 'menu_carrinho', combo_em_montagem = NULL, item_pendente_combo = NULL, carrinho_json = '{json.dumps(carrinho)}'::jsonb, ultima_interacao = NOW() WHERE jid = '{jid}';"
            sucesso_msg = (
                "🎟️ *Combo com Desconto de Cupom* adicionado ao carrinho com sucesso!"
                if usa_cupom
                else "✅ *Combo* adicionado ao carrinho com sucesso!"
            )

            return {
                "sql_update": sql_finalizacao,
                "payload": {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": telefone_real,
                    "type": "text",
                    "text": {"body": f"{sucesso_msg}\n\nO que deseja fazer agora?"},
                },
            }
        else:
            sql_progresso = f"UPDATE conversas_bot SET combo_em_montagem = '{json.dumps(combo)}'::jsonb, item_pendente_combo = NULL, estado_conversa = 'montando_combo_item', ultima_interacao = NOW() WHERE jid = '{jid}';"
            return {
                "sql_update": sql_progresso,
                "payload": {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": telefone_real,
                    "type": "text",
                    "text": {
                        "body": "✅ Quantidade registrada! Escolha o próximo item do combo:"
                    },
                },
            }

    return {
        "sql_update": f"UPDATE conversas_bot SET estado_conversa='menu_inicio', combo_em_montagem=NULL WHERE jid='{jid}';",
        "payload": {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real,
            "type": "text",
            "text": {"body": "⚠️ Estado de combo não reconhecido."},
        },
    }
