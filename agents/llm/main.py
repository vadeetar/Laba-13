import asyncio
import json
import logging
import os
import sys

from nats.aio.client import Client as NATS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        *(
            [logging.FileHandler(os.getenv("LOG_FILE", "/app/logs/llm.log"))]
            if os.getenv("LOG_FILE")
            else []
        ),
    ],
)
logger = logging.getLogger("llm-agent")


def analyze_symptoms(symptoms) -> dict:
    if isinstance(symptoms, list):
        text = " ".join(str(s).lower() for s in symptoms)
    else:
        text = str(symptoms).lower()

    urgent_keywords = ("fever", "температура", "chest pain", "боль в груди", "одышка")
    if any(k in text for k in urgent_keywords):
        return {
            "analysis": "urgent",
            "recommendation": "Рекомендуется срочная консультация врача",
            "confidence": 0.92,
        }
    return {
        "analysis": "normal",
        "recommendation": "Плановое наблюдение, при ухудшении — повторный визит",
        "confidence": 0.81,
    }


async def main():
    nc = NATS()
    await nc.connect(os.getenv("NATS_URL", "nats://nats:4222"))
    logger.info("LLM Agent connected")

    async def handler(msg):
        try:
            data = json.loads(msg.data.decode())
            result = analyze_symptoms(data.get("symptoms", ""))
            result["task_id"] = data.get("id", "")
            payload = json.dumps(result).encode()
            if msg.reply:
                await nc.publish(msg.reply, payload)
            else:
                await nc.publish("tasks.llm.done", payload)
            logger.info("analysis=%s task=%s", result["analysis"], result.get("task_id"))
        except Exception as exc:
            logger.error("handler error: %s", exc)

    await nc.subscribe("tasks.llm", cb=handler)
    await asyncio.Future()


asyncio.run(main())
