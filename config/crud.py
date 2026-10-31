import logging
from config.database import obter_conexao, db_pool

logger = logging.getLogger(__name__)


async def obter_estado_cliente(telefone: str) -> dict:
    """
    Busca os dados do cliente na tabela conversas_bot para alimentar o orquestrador.
    """
    conexao = await obter_conexao()
    try:
        # Busca pelo telefone real ou pelo JID da Meta
        query = (
            "SELECT * FROM conversas_bot WHERE telefone_real = $1 OR jid = $1 LIMIT 1"
        )
        registro = await conexao.fetchrow(query, telefone)

        # Converte o Record do asyncpg para um dicionário padrão do Python
        return dict(registro) if registro else None
    except Exception as e:
        logger.error(f"Erro ao buscar estado do cliente {telefone}: {e}")
        return None
    finally:
        # DEVOLVE A CONEXÃO À POOL
        if db_pool and conexao:
            await db_pool.release(conexao)


async def atualizar_estado_cliente(telefone: str, estado: str, etapa: str = ""):
    """
    Atualiza o estado atual do cliente no banco de dados para avançar na navegação.
    """
    conexao = await obter_conexao()
    try:
        query = """
            UPDATE conversas_bot 
            SET estado_conversa = $1, ultima_interacao = NOW() 
            WHERE telefone_real = $2 OR jid = $2
        """
        await conexao.execute(query, estado, telefone)
    except Exception as e:
        logger.error(f"Erro ao atualizar estado do cliente {telefone}: {e}")
    finally:
        # DEVOLVE A CONEXÃO À POOL
        if db_pool and conexao:
            await db_pool.release(conexao)
