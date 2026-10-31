import json
import logging
import os
import httpx

logger = logging.getLogger(__name__)
CHATWOOT_BASE_URL = os.getenv("CHATWOOT_API_URL")


async def processar_pedido(
    dados_cliente: dict, mensagem_cliente: str, db_connection, chatwoot_headers: dict
) -> dict:
    opcao_escolhida = mensagem_cliente.strip()
    telefone_real = dados_cliente.get("telefone_real")
    jid = dados_cliente.get("jid")

    if opcao_escolhida == "2":
        sql_update = f"UPDATE conversas_bot SET estado_conversa = 'cadastra_endereco', expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{jid}';"
        return {
            "sql_update": sql_update,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real or jid,
                "type": "text",
                "text": {
                    "body": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\nOk _{dados_cliente.get('primeiro_nome', '')}_!\nVamos atualizar o seu\nendereço para conseguir\nfazer o cálculo do\nvalor do *FRETE* 🛵\n\nAtualize o *ENDEREÇO* abaixo:"
                },
            },
        }

    if opcao_escolhida not in ["1", "2"]:
        return {
            "sql_update": None,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real or jid,
                "type": "text",
                "text": {
                    "body": f"_*_{dados_cliente.get('primeiro_nome', '')}_*_, sua mensagem\nnão é válida. Seu endereço está correto?"
                },
            },
        }

    carrinho_raw = dados_cliente.get("carrinho_json", [])
    try:
        carrinho_json = (
            json.loads(carrinho_raw) if isinstance(carrinho_raw, str) else carrinho_raw
        )
    except Exception:
        carrinho_json = []

    valor_pedido = float(dados_cliente.get("valor_pedido", 0))
    cupom_promo = dados_cliente.get("cupom_promo")
    cupom_db = None if not cupom_promo or cupom_promo == "null" else cupom_promo

    # INSERT obrigatoriamente roda no subfluxo para obter o número via RETURNING
    query_insert = """
        INSERT INTO pedidos (jid, telefone_real, primeiro_nome, nome_cliente, carrinho_json, valor_total, status_pedido, cupom_promo)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, 'PAGAMENTO_PENDENTE', $7) RETURNING 'TLF-' || numero_pedido;
    """
    resultado_db = await db_connection.fetchrow(
        query_insert,
        jid,
        telefone_real,
        dados_cliente.get("primeiro_nome"),
        dados_cliente.get("nome_cliente"),
        json.dumps(carrinho_json),
        valor_pedido,
        cupom_db,
    )
    numero_pedido_formatado = resultado_db[0] if resultado_db else "TLF-0000"

    desconto_num = float(dados_cliente.get("desconto_aplicado", 0) or 0)
    carrinho_texto = ""
    qtd_trufas = 0

    for item in carrinho_json:
        qtd = item.get("qtd", 0)
        preco = item.get("precoUnitario", 0)
        nome_item = item.get("nome", "").strip()
        if "combo" not in nome_item.lower():
            qtd_trufas += qtd
        carrinho_texto += (
            f"*{item.get('indice', '?')})* {'📦' if 'combo' in nome_item.lower() else '🍫'} {nome_item}\n\n*Quantidade:* {qtd}\n*Preço:* R$ {preco:,.2f} *(R$ {qtd*preco:,.2f})*\n\n".replace(
                ",", "X"
            )
            .replace(".", ",")
            .replace("X", ".")
        )
        if itens_int := item.get("itens_internos"):
            carrinho_texto += "*Itens do combo:*\n"
            agrupados = {}
            for interno in itens_int:
                agrupados[interno.get("nome")] = (
                    agrupados.get(interno.get("nome"), 0) + 1
                )
            for n_int, q_int in agrupados.items():
                carrinho_texto += f"▫️ {q_int}x {n_int}\n"
            carrinho_texto += "\n"
        carrinho_texto += "--------------------------------------------------------\n\n"

    resumo_cliente = carrinho_texto
    if desconto_num > 0:
        resumo_cliente += (
            f"💸→ DESCONTO:\n*R$ {desconto_num:,.2f}*\n\n".replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )
    resumo_cliente += f"🪙→ VALOR PEDIDO:\n*{f'R$ {valor_pedido:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')}*\n\n"

    cep_str = str(dados_cliente.get("cep", ""))
    cep_fmt = f"{cep_str[:5]}-{cep_str[5:]}" if len(cep_str) >= 5 else cep_str
    resumo_chatwoot = f"🛍️→ PEDIDO: *{numero_pedido_formatado}*\n\n----------------------------------------------------------\n\n{resumo_cliente}--------------------------------------------------------\n\n*📍→ RUA/Nº:*\n\n{dados_cliente.get('endereco', '')}\n\n*📍→ BAIRRO:*\n\n{dados_cliente.get('bairro', '')}\n\n*📍→ CEP:*\n\n{cep_fmt}\n\n*📍→ COMPLEMENTO:*\n\n{dados_cliente.get('complemento', '')}\n​"
    if qtd_trufas >= 2:
        resumo_chatwoot += f"\n\n🚨 *PROMO DESBLOQUEADA:* Este cliente tem {qtd_trufas} trufas. Ofereça a promoção!"

    telefone_busca = telefone_real or ""
    async with httpx.AsyncClient() as client:
        resp_busca = await client.get(
            f"{CHATWOOT_BASE_URL}/contacts/search?q={telefone_busca}",
            headers=chatwoot_headers,
        )
        contato = next(
            (
                c
                for c in resp_busca.json().get("payload", [])
                if (c.get("phone_number") or "").replace("+", "").strip()
                == telefone_busca.replace("+", "").strip()
                or (c.get("contact_inboxes", [{}])[0].get("source_id") or "").strip()
                == telefone_busca.replace("+", "").strip()
            ),
            None,
        )

        source_id = conversation_id = None
        if contato:
            source_id = contato.get("contact_inboxes", [{}])[0].get("source_id")
            resp_convs = await client.get(
                f"{CHATWOOT_BASE_URL}/conversations?status=open",
                headers=chatwoot_headers,
            )
            conversation_id = next(
                (
                    conv.get("id")
                    for conv in resp_convs.json().get("data", {}).get("payload", [])
                    if conv.get("messages")
                    and conv["messages"][0]
                    .get("conversation", {})
                    .get("contact_inbox", {})
                    .get("source_id")
                    == source_id
                ),
                None,
            )
        else:
            novo_c = await client.post(
                f"{CHATWOOT_BASE_URL}/contacts",
                json={
                    "inbox_id": 1,
                    "name": dados_cliente.get("nome_cliente"),
                    "blocked": False,
                    "phone_number": f"+{telefone_busca}",
                    "identifier": telefone_busca,
                },
                headers=chatwoot_headers,
            )
            source_id = (
                novo_c.json()
                .get("payload", {})
                .get("contact_inbox", {})
                .get("source_id")
            )
            nova_conv = await client.post(
                f"{CHATWOOT_BASE_URL}/conversations",
                json={"source_id": source_id, "inbox_id": 15},
                headers=chatwoot_headers,
            )
            conversation_id = nova_conv.json().get("id")

        if conversation_id:
            await client.post(
                f"{CHATWOOT_BASE_URL}/conversations/{conversation_id}/assignments",
                json={"assignee_id": 1},
                headers=chatwoot_headers,
            )
            await client.post(
                f"{CHATWOOT_BASE_URL}/conversations/{conversation_id}/labels",
                json={"labels": ["novo_pedido"]},
                headers=chatwoot_headers,
            )
            await client.post(
                f"{CHATWOOT_BASE_URL}/conversations/{conversation_id}/messages",
                json={
                    "content": resumo_chatwoot,
                    "message_type": "outgoing",
                    "private": True,
                    "content_type": "text",
                },
                headers=chatwoot_headers,
            )

    sql_pausa_bot = f"UPDATE conversas_bot SET estado_conversa = 'aguardando_frete', is_bot_paused = TRUE, expirando = FALSE, ultima_interacao = NOW() WHERE jid = '{jid}';"

    msg_wa = f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n🛍️ PEDIDO: *{numero_pedido_formatado}*\n\n---------------------------------------------------\n\n_*{dados_cliente.get('nome_cliente', '')}*_,\nestou calculando o\nvalor do *FRETE* 🛵...\n\nAguarde...⏳\nㅤ"

    return {
        "sql_update": sql_pausa_bot,
        "payload": {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real or jid,
            "type": "text",
            "text": {"body": msg_wa},
        },
    }
