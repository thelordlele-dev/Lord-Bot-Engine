import json
import logging

# IMPORTANDO OS SUBFLUXOS PARA DELEGAR AS AÇÕES DIRETAMENTE!
from subfluxos.cardapio import processar_busca_cardapio
from subfluxos.cliente_retorna_menu import processar_retorno_menu
from subfluxos.gerenciador_encerramento import processar_encerramento_sessao

logger = logging.getLogger(__name__)

async def roteia_adicionar_mais_itens(
    user_id: str,
    telefone_real: str,
    primeiro_nome: str,
    mensagem_cliente: str,
    cliente_db: dict, # Agora recebe o DB inteiro para extrair o que precisar!
) -> dict:
    """
    [MÓDULO 1.26 / 1.27 - Adiciona Mais Itens / Adiciona Mais Itens Cupom]
    Encaminha o cliente para a secção correta do cardápio consoante a opção selecionada.
    """
    opcao = str(mensagem_cliente).strip()
    
    # Extraímos as variáveis necessárias do banco
    pagina_atual = cliente_db.get("pagina_atual", 1)
    mapa_id_json = cliente_db.get("mapa_id_json", "{}")
    carrinho = cliente_db.get("carrinho_json", "[]")

    # =======================================================================
    # OPÇÃO 1: Buscar itens "Individuais"
    # =======================================================================
    if opcao == "1":
        return await processar_busca_cardapio(
            user_id, telefone_real, primeiro_nome, "Individuais", pagina_atual, mapa_id_json
        )

    # =======================================================================
    # OPÇÃO 2: Buscar "Combos"
    # =======================================================================
    elif opcao == "2":
        return await processar_busca_cardapio(
            user_id, telefone_real, primeiro_nome, "Combos", pagina_atual, mapa_id_json
        )

    # =======================================================================
    # OPÇÃO 3: Retorna ao Menu Principal
    # =======================================================================
    elif opcao == "3":
        return await processar_retorno_menu(user_id, telefone_real, cliente_db)

    # =======================================================================
    # OPÇÃO 4: Sair
    # =======================================================================
    elif opcao == "4":
        return await processar_encerramento_sessao(
            user_id, telefone_real, primeiro_nome, carrinho, "sair"
        )

    # =======================================================================
    # ERRO / Opção inválida (Devolve menu interativo atualizado com 4 opções)
    # =======================================================================
    else:
        mensagem_erro = (
            f"_{primeiro_nome}_, sua mensagem\nnão é válida. Por favor"
            " escolha\numa das opções abaixo:"
        )
        # SQL apenas para manter a conversa ativa
        sql_update = f"UPDATE conversas_bot SET ultima_interacao = NOW() WHERE jid = '{user_id}';"
        
        return {
            "sql_update": sql_update,
            "payload": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone_real,
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {
                        "text": f"_*👸🏾 Kakaw - TheLordTrufas.*_\n\n{mensagem_erro}\n"
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
                                    {"id": "3", "title": "🔙 Menu Principal"},
                                    {"id": "4", "title": "❌ Sair"},
                                ],
                            }
                        ],
                    },
                },
            },
        }