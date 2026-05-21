import asyncio
import json
import logging
import os
import sys

import httpx
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

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")


def symptoms_text(symptoms) -> str:
    if isinstance(symptoms, list):
        return ", ".join(str(s) for s in symptoms)
    return str(symptoms)


def analyze_fallback(symptoms) -> dict:
    text = symptoms_text(symptoms).lower()
    urgent_keywords = ("fever", "температура", "chest pain", "боль в груди", "одышка")
    if any(k in text for k in urgent_keywords):
        return {
            "analysis": "urgent",
            "recommendation": "Рекомендуется срочная консультация врача",
            "confidence": 0.85,
            "source": "rules-fallback",
        }
    return {
        "analysis": "normal",
        "recommendation": "Плановое наблюдение, при ухудшении — повторный визит",
        "confidence": 0.75,
        "source": "rules-fallback",
    }


async def analyze_with_ollama(symptoms) -> dict:
    text = symptoms_text(symptoms)
    prompt = (
        "Ты медицинский ассистент. Проанализируй симптомы пациента и ответь ТОЛЬКО JSON "
        'с полями: analysis (urgent|normal), recommendation (строка), confidence (0-1). '
        f"Симптомы: {text}"
    )
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"{OLLAMA_URL.rstrip('/')}/api/generate",
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            )
            if resp.status_code != 200:
                logger.warning("Ollama HTTP %s", resp.status_code)
                return analyze_fallback(symptoms)

            raw = resp.json().get("response", "")
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                parsed = json.loads(raw[start : end + 1])
                parsed["source"] = "ollama"
                return parsed
    except Exception as exc:
        logger.warning("Ollama unavailable (%s), using fallback", exc)

    return analyze_fallback(symptoms)


async def main():
    nc = NATS()
    await nc.connect(os.getenv("NATS_URL", "nats://nats:4222"))
    logger.info("LLM Agent connected (Ollama=%s model=%s)", OLLAMA_URL, OLLAMA_MODEL)

    async def handler(msg):
        try:
            data = json.loads(msg.data.decode())
            result = await analyze_with_ollama(data.get("symptoms", ""))
            result["task_id"] = data.get("id", "")
            payload = json.dumps(result, ensure_ascii=False).encode()
            if msg.reply:
                await nc.publish(msg.reply, payload)
            else:
                await nc.publish("tasks.llm.done", payload)
            logger.info("analysis=%s source=%s", result["analysis"], result.get("source"))
        except Exception as exc:
            logger.error("handler error: %s", exc)

    await nc.subscribe("tasks.llm", cb=handler)
    await asyncio.Future()


asyncio.run(main())
