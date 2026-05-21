import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

import nats
from nats.errors import TimeoutError as NatsTimeoutError

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import settings

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

os.makedirs(os.path.dirname(settings.log_file), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [orchestrator] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(settings.log_file, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OpenTelemetry
# ---------------------------------------------------------------------------

otlp_endpoint = settings.otel_exporter_otlp_endpoint.rstrip("/")
if not otlp_endpoint.endswith("/v1/traces"):
    otlp_endpoint = f"{otlp_endpoint}/v1/traces"

trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
)

# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Система поддержки пациентов",
    description="Лабораторная работа №13, вариант 18 — MAS",
    version="1.0.0",
)

nc: Optional[nats.NATS] = None
tasks_processed = 0
last_auction_winner: Optional[dict] = None

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PatientRegisterRequest(BaseModel):
    patient_id: str
    first_name: str
    last_name: str
    symptoms: list[str] = Field(default_factory=list)
    urgency: str = "normal"
    appointment_date: Optional[str] = None
    rating: int = Field(default=5, ge=1, le=5)


class LegacyProcessRequest(BaseModel):
    patient: str
    symptoms: str
    date: str


# ---------------------------------------------------------------------------
# Auction & autoscaling
# ---------------------------------------------------------------------------

APPOINTMENT_AGENTS = [
    {"name": "appointment-agent", "cost": 3, "skill": 0.95},
    {"name": "appointment-agent-2", "cost": 1, "skill": 0.80},
]


def choose_appointment_agent() -> dict:
    """Аукцион: выбираем агента с минимальной стоимостью."""
    global last_auction_winner
    winner = min(APPOINTMENT_AGENTS, key=lambda x: (x["cost"], -x["skill"]))
    last_auction_winner = winner
    logger.info(
        "Auction winner: %s (cost=%s, skill=%s)",
        winner["name"],
        winner["cost"],
        winner["skill"],
    )
    return winner


def autoscaling_check(queue_size: int = 15) -> bool:
    if queue_size > settings.queue_scale_threshold:
        logger.warning(
            "Autoscaling: queue_size=%d > %d — запуск дополнительного агента",
            queue_size,
            settings.queue_scale_threshold,
        )
        return True
    return False


# ---------------------------------------------------------------------------
# NATS helpers
# ---------------------------------------------------------------------------


async def nats_request(
    subject: str,
    payload: dict,
    timeout: Optional[float] = None,
    retries: Optional[int] = None,
) -> dict:
    if nc is None:
        raise HTTPException(status_code=503, detail="NATS not connected")

    timeout = timeout or settings.request_timeout
    retries = retries or settings.max_retries
    data = json.dumps(payload, ensure_ascii=False).encode()
    last_error: Optional[Exception] = None

    for attempt in range(1, retries + 1):
        try:
            with tracer.start_as_current_span(f"nats.request.{subject}"):
                msg = await nc.request(subject, data, timeout=timeout)
                return json.loads(msg.data.decode())
        except (NatsTimeoutError, asyncio.TimeoutError, Exception) as exc:
            last_error = exc
            logger.warning(
                "Retry %d/%d for %s failed: %s",
                attempt,
                retries,
                subject,
                exc,
            )
            if attempt < retries:
                await asyncio.sleep(0.3 * attempt)

    raise HTTPException(
        status_code=504,
        detail=f"Агент '{subject}' не ответил после {retries} попыток: {last_error}",
    )


def default_appointment_date() -> str:
    return (datetime.utcnow() + timedelta(days=3)).strftime("%Y-%m-%d")


async def run_patient_pipeline(body: PatientRegisterRequest) -> dict:
    global tasks_processed

    task_id = str(uuid.uuid4())
    patient_name = f"{body.first_name} {body.last_name}".strip()
    appointment_date = body.appointment_date or default_appointment_date()

    with tracer.start_as_current_span("patient-pipeline") as span:
        span.set_attribute("patient.id", body.patient_id)
        autoscaling_check()

        # 1. Триаж
        triage_result = await nats_request(
            "tasks.triage",
            {
                "id": task_id,
                "patient": patient_name,
                "symptoms": body.symptoms,
                "urgency": body.urgency,
            },
        )

        # 2. LLM-анализ симптомов
        llm_result = await nats_request(
            "tasks.llm",
            {
                "id": task_id,
                "patient": patient_name,
                "symptoms": body.symptoms,
            },
        )

        # 3. Запись к врачу (аукцион)
        auction_winner = choose_appointment_agent()
        appointment_result = await nats_request(
            "tasks.appointment",
            {
                "id": task_id,
                "patient": patient_name,
                "date": appointment_date,
                "specialty": triage_result.get("specialty", "терапевт"),
                "agent_cost": auction_winner["cost"],
                "preferred_agent": auction_winner["name"],
            },
        )

        # 4. Напоминание
        reminder_result = await nats_request(
            "tasks.reminder",
            {
                "id": task_id,
                "patient": patient_name,
                "date": appointment_date,
            },
        )

        # 5. Обратная связь (stateful / Redis)
        feedback_result = await nats_request(
            "tasks.feedback",
            {
                "id": task_id,
                "patient": patient_name,
                "rating": body.rating,
            },
        )

        tasks_processed += 1

        return {
            "task_id": task_id,
            "patient_id": body.patient_id,
            "patient": patient_name,
            "appointment_date": appointment_date,
            "auction": auction_winner,
            "triage": triage_result,
            "llm": llm_result,
            "appointment": appointment_result,
            "reminder": reminder_result,
            "feedback": feedback_result,
        }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def startup():
    global nc
    nc = await nats.connect(settings.nats_url)
    logger.info("Connected to NATS at %s", settings.nats_url)


@app.on_event("shutdown")
async def shutdown():
    if nc:
        await nc.close()
        logger.info("NATS connection closed")


@app.get("/health")
async def health():
    return {"status": "ok", "nats": nc is not None and nc.is_connected}


@app.get("/status")
async def status():
    return {
        "variant": 18,
        "domain": "Система поддержки пациентов",
        "agents": [
            "triage-agent",
            "appointment-agent",
            "appointment-agent-2",
            "reminder-agent",
            "feedback-agent",
            "llm-agent",
        ],
        "tasks_processed": tasks_processed,
        "last_auction_winner": last_auction_winner,
        "jaeger_ui": "http://localhost:16686",
    }


@app.get("/monitor", response_class=HTMLResponse)
async def monitor():
    winner = last_auction_winner or {}
    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head><meta charset="utf-8"><title>MAS Monitor — Вариант 18</title>
    <style>body{{font-family:sans-serif;margin:2rem;background:#f5f7fb}}
    .card{{background:#fff;padding:1.5rem;border-radius:8px;max-width:720px;box-shadow:0 2px 8px #0001}}</style>
    </head>
    <body>
    <div class="card">
    <h1>🏥 Мониторинг агентов</h1>
    <p><b>Обработано задач:</b> {tasks_processed}</p>
    <p><b>Аукцион (последний победитель):</b> {winner.get("name", "—")} (cost={winner.get("cost", "—")})</p>
    <p><b>Jaeger:</b> <a href="http://localhost:16686" target="_blank">localhost:16686</a></p>
    <p><b>API:</b> POST /patients/register</p>
    </div>
    </body></html>
    """


@app.post("/patients/register")
async def register_patient(body: PatientRegisterRequest):
    logger.info("Register patient_id=%s urgency=%s", body.patient_id, body.urgency)
    try:
        result = await run_patient_pipeline(body)
        logger.info("Pipeline completed task_id=%s", result["task_id"])
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Pipeline error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/process")
async def process_legacy(body: LegacyProcessRequest):
    """Совместимость со старым API."""
    mapped = PatientRegisterRequest(
        patient_id=str(uuid.uuid4())[:8],
        first_name=body.patient,
        last_name="",
        symptoms=[body.symptoms],
        appointment_date=body.date,
    )
    return await register_patient(mapped)
