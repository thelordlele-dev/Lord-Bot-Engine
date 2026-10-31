import os
import json
import aio_pika
from dotenv import load_dotenv

load_dotenv()

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")


async def publicar_na_fila(nome_fila: str, mensagem: dict):
    """
    Publica uma mensagem em uma fila quorum do RabbitMQ de forma assíncrona.
    """
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        # Declara a fila como quorum
        queue = await channel.declare_queue(
            nome_fila, durable=True, arguments={"x-queue-type": "quorum"}
        )

        # TRANSFORMA PARA JSON VÁLIDO ANTES DE CODIFICAR
        body = json.dumps(mensagem).encode("utf-8")
        await channel.default_exchange.publish(
            aio_pika.Message(body=body), routing_key=queue.name
        )
