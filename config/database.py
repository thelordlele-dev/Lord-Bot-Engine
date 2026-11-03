import os
import asyncpg
from dotenv import load_dotenv
import asyncio

_lock_pool = None

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "conversas_bot")

db_pool = None


async def conectar_db():
    global db_pool, _lock_pool
    if _lock_pool is None:
        _lock_pool = asyncio.Lock()
    async with _lock_pool:
        if db_pool is None:
            db_pool = await asyncpg.create_pool(
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                host=DB_HOST,
                port=DB_PORT,
                min_size=2,
                max_size=10,
                # ========================================================
                # 🛡️ CONFIGURAÇÕES SALVA-VIDAS (ANTI-TRAVAMENTO) 🛡️
                # ========================================================
                command_timeout=60,  # Timeout para evitar queries presas
                max_inactive_connection_lifetime=300,  # Recicla conexões inativas por 5 min
                server_settings={
                    "tcp_keepalives_idle": "60",  # Ping na rede a cada 60s
                    "tcp_keepalives_interval": "10",
                    "tcp_keepalives_count": "5",
                },
                # ========================================================
            )


async def desconectar_db():
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None


async def obter_conexao():
    global db_pool
    if not db_pool:
        await conectar_db()
    # Se a pool esgotar, falha com erro em vez de travar em silêncio
    return await db_pool.acquire(timeout=10)


async def liberar_conexao(conexao):
    if conexao is not None and db_pool:
        await db_pool.release(conexao)
