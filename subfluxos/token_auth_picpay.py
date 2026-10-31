import logging
import httpx
import os
from subfluxos.loja import obter_status_atual_loja

logger = logging.getLogger(__name__)

CLIENT_ID = os.getenv("PICPAY_CLIENT_ID")
CLIENT_SECRET = os.getenv("PICPAY_CLIENT_SECRET")
PICPAY_OAUTH_URL = os.getenv("PICPAY_OAUTH_URL")
NOTION_TOKEN = os.getenv("NOTION_API_KEY")


async def executar_ciclo_token_picpay(db_connection=None):
    try:
        status_loja = await obter_status_atual_loja()
        if not status_loja.get("aberta", False):
            return

        payload = {
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                PICPAY_OAUTH_URL,
                data=payload,
                headers={"Accept": "application/json"},
                timeout=30,
            )

        if response.status_code == 200:
            dados = response.json()
            account_id = (
                dados.get("authorization_details", [{}])[0].get("account_id", "")
                if dados.get("authorization_details")
                else ""
            )

            if db_connection:
                await db_connection.execute(
                    """
                    INSERT INTO picpay_tokens (id, access_token, account_id, ultima_atualizacao) 
                    VALUES (1, $1, $2, NOW() AT TIME ZONE 'America/Sao_Paulo') 
                    ON CONFLICT (id) DO UPDATE SET access_token = EXCLUDED.access_token, account_id = EXCLUDED.account_id, ultima_atualizacao = NOW() AT TIME ZONE 'America/Sao_Paulo';
                    """,
                    f"Bearer {dados.get('access_token')}",
                    account_id,
                )
        else:
            logger.error("Erro PicPay API: %s", response.text)
    except Exception as e:
        logger.error("Exceção Token PicPay: %s", str(e))
