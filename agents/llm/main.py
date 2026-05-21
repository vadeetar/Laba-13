import asyncio, json, os
from nats.aio.client import Client as NATS


async def main():
    nc = await NATS().connect(os.getenv("NATS_URL", "nats://nats:4222"))

    async def handler(msg):
        data = json.loads(msg.data)
        # Имитация "умного" анализа
        result = {"analysis": "urgent" if "fever" in data.get("symptoms", "") else "normal"}
        await nc.publish(msg.reply, json.dumps(result).encode())

    await nc.subscribe("llm.analyze", handler)
    await asyncio.Future()


asyncio.run(main())