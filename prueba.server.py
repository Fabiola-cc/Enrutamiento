import asyncio
import json
import redis.asyncio as redis
from MessageStruct import Message
from Node import Node  
from dotenv import load_dotenv
import os

load_dotenv()
HOST = os.getenv("REDIS_HOST")
PORT = int(os.getenv("REDIS_PORT", 6379))
PWD = os.getenv("REDIS_PWD")

NODE_NAME = "A"  # Cambiar según este nodo
CHANNEL = f"sec30.grupo7.{NODE_NAME.lower()}"

NEIGHBORS = ["B", "C"]  # solo nombres

async def redis_reader(node: Node, pubsub: redis.client.PubSub):
    while True:
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
        if message:
            data = message["data"]
            if isinstance(data, bytes):
                data = data.decode()
            print(f"[{NODE_NAME}] Mensaje recibido: {data}")

            try:
                msg_json = json.loads(data)
                msg_obj = Message.from_dict(msg_json)
                await node.receive_message_async(msg_obj)
            except Exception as e:
                print(f"[{NODE_NAME}] Error procesando mensaje: {e}")

async def send_message_redis(r: redis.Redis, message: Message):
    channel = CHANNEL
    msg_json = json.dumps(message.to_dict())
    await r.publish(channel, msg_json)
    print(f"[{NODE_NAME}] Enviado mensaje a {channel}: {message.payload}")

async def main():
    r = redis.Redis(host=HOST, port=PORT, password=PWD)

    # Crear solo este nodo
    node = Node(NODE_NAME)

    # Agregar vecinos como nombres, no objetos (los usaremos para enviar Redis)
    node.neighbor_names = NEIGHBORS

    async with r.pubsub() as pubsub:
        await pubsub.subscribe(CHANNEL)
        print(f"[{NODE_NAME}] Suscrito a canal {CHANNEL}")

        reader_task = asyncio.create_task(redis_reader(node, pubsub))

        # Mensaje de prueba a un vecino
        test_msg = Message(
            proto="flooding",
            mtype="message",
            from_node=NODE_NAME,
            to_node=NEIGHBORS[0],  # enviar al primer vecino
            ttl=5,
            payload=f"Hola desde {NODE_NAME} usando REDIS!"
        )
        await send_message_redis(r, test_msg)

        await reader_task

if __name__ == "__main__":
    print(f"[{NODE_NAME}] Iniciando nodo con Redis Async...")
    asyncio.run(main())
