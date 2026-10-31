import json
import logging
import re

logger = logging.getLogger(__name__)


async def processar_retorno_bot_pagamento(
    payload_recebido: dict, db_connection
) -> dict:
    body = payload_recebido.get("body", {})
    headers_prop = payload_recebido.get("properties", {}).get("headers", {})

    telefone_real = (
        str(headers_prop.get("telefone_real", "")).replace("+", "").strip()
        if headers_prop
        else ""
    )
    valor_pedido_str = (
        str(headers_prop.get("valor_pedido", "0")).replace(",", ".")
        if headers_prop
        else "0"
    )
    source_id = str(headers_prop.get("source_id", "")).strip() if headers_prop else ""
    numero_pedido_str = (
        str(headers_prop.get("numero_pedido", "")).strip() if headers_prop else ""
    )

    if not telefone_real or not numero_pedido_str or valor_pedido_str == "0":
        meta_sender = body.get("meta", {}).get("sender", {})
        if not telefone_real:
            telefone_real = meta_sender.get("phone_number", "").replace("+", "").strip()
        messages = body.get("messages", [])
        conteudo_msg = messages[0].get("content", "") if messages else ""
        if not source_id and messages:
            source_id = (
                messages[0]
                .get("conversation", {})
                .get("contact_inbox", {})
                .get("source_id", "")
                .strip()
            )

        if valor_pedido_str == "0" or not valor_pedido_str:
            if match := re.search(
                r"VALOR TOTAL:[\s\S]*?R\$\s*([\d.,]+)", conteudo_msg, re.IGNORECASE
            ):
                valor_pedido_str = match.group(1).replace(".", "").replace(",", ".")

        if not numero_pedido_str and "PEDIDO:" in conteudo_msg:
            try:
                numero_pedido_str = conteudo_msg.split("PEDIDO:")[1].strip()[:15]
            except Exception:
                numero_pedido_str = ""

    valor_pedido_num = float(valor_pedido_str) if valor_pedido_str else 0.0
    numero_pedido_limpo = numero_pedido_str.replace("TLF-", "").strip()

    if db_connection and telefone_real:
        await db_connection.execute(
            "UPDATE conversas_bot SET valor_pedido = $1, telefone_real = $2, ultima_interacao = NOW() WHERE telefone_real = $2",
            valor_pedido_num,
            telefone_real,
        )
    if db_connection and numero_pedido_limpo:
        await db_connection.execute(
            "UPDATE pedidos SET valor_total = $1, telefone_real = $2 WHERE numero_pedido = $3",
            valor_pedido_num,
            telefone_real,
            numero_pedido_limpo,
        )

    # NOVIDADE: Em vez de mandar para uma fila, já chama a criação do link de pagamento direto!
    from subfluxos.cria_pagamento import processar_criacao_pagamento

    # Criamos um "falso" cliente_db só com os dados que o cria_pagamento precisa
    dados_estado = {
        "valor_pedido": valor_pedido_num,
        "numero_pedido": numero_pedido_limpo,
    }

    # Executa a geração do link do PicPay/Mercado Pago
    return await processar_criacao_pagamento(
        user_id=source_id or telefone_real,
        telefone_real=telefone_real,
        primeiro_nome="Cliente",
        dados_estado=dados_estado,
    )
