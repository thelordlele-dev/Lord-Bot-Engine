from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)


async def verificar_e_expirar_cupons(db_connection=None) -> dict:
    clientes = []
    if db_connection:
        clientes = await db_connection.fetch(
            "SELECT jid, data_compra, validade_cupom FROM conversas_bot WHERE cupom IS NOT NULL;"
        )
    if not clientes:
        return {"cupons_expirados_removidos": 0}

    removidos = 0
    agora = datetime.now(timezone.utc)

    for cliente in clientes:
        jid = cliente["jid"]
        dias_validade = int(cliente.get("validade_cupom") or 0)

        if cliente.get("data_compra") and dias_validade > 0:
            try:
                data_compra = cliente["data_compra"]
                if isinstance(data_compra, str):
                    data_compra = datetime.fromisoformat(
                        data_compra.replace("Z", "+00:00")
                    )
                if data_compra.tzinfo is None:
                    data_compra = data_compra.replace(tzinfo=timezone.utc)

                if agora > (data_compra + timedelta(days=dias_validade)):
                    if db_connection:
                        await db_connection.execute(
                            "UPDATE conversas_bot SET cupom = NULL, desconto = NULL, validade_cupom = NULL, valor_minimo_cupom = NULL WHERE jid = $1;",
                            jid,
                        )
                    removidos += 1
            except Exception as e:
                logger.error("Erro cupom JID %s: %s", jid, str(e))

    return {"cupons_expirados_removidos": removidos}
