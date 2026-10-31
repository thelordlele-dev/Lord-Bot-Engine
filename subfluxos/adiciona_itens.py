import json
import logging

# 1. IMPORTAMOS O NOSSO SUPER GERENCIADOR AQUI NO TOPO!
from subfluxos.gerenciador_encerramento import processar_encerramento_sessao

logger = logging.getLogger(__name__)


async def processar_adiciona_itens(
    user_id: str,
    telefone_real: str,
    primeiro_nome: str,
    mensagem_cliente: str,
    cliente_db: dict,  # 2. MUDAMOS AQUI: Agora ele recebe o dicionário do banco de dados (o worker já envia assim)
) -> dict:
    """
    [MÓDULO UNIFICADO - Adiciona Itens / Cupom / Frete]
    Gerencia as escolhas do cliente após interagir com o carrinho ou avisos de mínimo:
    - Opção '1': Adicionar mais itens / Ver Cardápio de Individuais
    - Opção '2': Ver Combos / Finalizar Pedido (dependendo do fluxo de origem)
    - Opção '3': Sair do atendimento
    """
    opcao = str(mensagem_cliente).strip()

    # Extraímos o estado atual de dentro do dicionário do banco
    estado_atual = cliente_db.get("estado_conversa", "")

    # =======================================================================
    # TRATAMENTO DA OPÇÃO 3: SAIR DO ATENDIMENTO
    # =======================================================================
    if opcao == "3" or opcao == "5":
        carrinho = cliente_db.get("carrinho_json", "[]")

        # 3. MÁGICA: Entregamos a responsabilidade para o Gerenciador de Encerramento!
        # Ele vai repor o estoque no Notion, fazer o SQL de RESET e devolver a mensagem de Tchau.
        return await processar_encerramento_sessao(
            user_id, telefone_real, primeiro_nome, carrinho, "sair"
        )

    # =======================================================================
    # TRATAMENTO DA OPÇÃO 1: ADICIONAR ITENS / INDIVIDUAIS
    # =======================================================================
    if opcao == "1":
        novo_estado = (
            "mais_itens_cupom" if "cupom" in estado_atual else "adiciona_mais_itens"
        )
        sql_update = f"""
            UPDATE conversas_bot 
            SET estado_conversa = '{novo_estado}', 
                expirando = FALSE, 
                mapa_id_json = '{{}}', 
                ultima_interacao = NOW() 
            WHERE jid = '{user_id}'
        """
        return {
            "proximo_estado": novo_estado,
            "sql_update": sql_update.strip(),
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {
                        "text": (
                            f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_{primeiro_nome}_,\nqual"
                            " cardápio você deseja visualizar?\n"
                        )
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
                                    {"id": "1", "title": "🍫 Individuais "},
                                    {"id": "2", "title": "📦 Combos"},
                                    {"id": "3", "title": "❌ Sair"},
                                ],
                            }
                        ],
                    },
                },
            },
        }

    # =======================================================================
    # TRATAMENTO DA OPÇÃO 2: COMBOS / OUTROS ITENS
    # =======================================================================
    if opcao == "2":
        sql_update = f"""
            UPDATE conversas_bot 
            SET estado_conversa = 'aguardando_categoria', 
                expirando = FALSE, 
                mapa_id_json = '{{}}', 
                ultima_interacao = NOW() 
            WHERE jid = '{user_id}'
        """
        return {
            "proximo_estado": "aguardando_categoria",
            "sql_update": sql_update.strip(),
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {
                        "text": (
                            f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_{primeiro_nome}_,\nqual"
                            " cardápio você deseja visualizar?\n"
                        )
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
                                    {"id": "1", "title": "🍫 Individuais "},
                                    {"id": "2", "title": "📦 Combos"},
                                    {"id": "3", "title": "❌ Sair"},
                                ],
                            }
                        ],
                    },
                },
            },
        }

    # =======================================================================
    # TRATAMENTO DE ENTRADA INVÁLIDA / ERRO
    # =======================================================================
    sql_update = f"""
        UPDATE conversas_bot 
        SET expirando = FALSE, 
            ultima_interacao = NOW() 
        WHERE jid = '{user_id}'
    """
    return {
        "proximo_estado": estado_atual,
        "sql_update": sql_update.strip(),
        "payload": {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone_real,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": (
                        f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n_{primeiro_nome}_, sua"
                        " mensagem\nnão é válida. Por favor escolha\numa das"
                        " opções abaixo:\n"
                    )
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
