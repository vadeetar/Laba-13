import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

import nats
from nats.errors import TimeoutError as NatsTimeoutError

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app import state
from app.auction import collect_auction_bids
from app.autoscale import (
    get_autoscale_events,
    get_redis,
    queue_depth,
    queue_pop,
    queue_push,
    try_scale_appointment_agents,
)
from app.config import settings
from app.tracing_util import nats_request_with_trace, tracer

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
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Система поддержки пациентов",
    description="Лабораторная работа №13, вариант 18 — MAS",
    version="2.0.0",
)

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "..", "templates"))

nc: Optional[nats.NATS] = None

AGENTS_META = [
    {"name": "triage-agent", "role": "Триаж симптомов", "status": "active"},
    {"name": "appointment-agent", "role": "Запись к врачу", "status": "active"},
    {"name": "appointment-agent-2", "role": "Запись (реплика)", "status": "active"},
    {"name": "reminder-agent", "role": "Напоминания", "status": "active"},
    {"name": "feedback-agent", "role": "Обратная связь + Redis", "status": "active"},
    {"name": "llm-agent", "role": "LLM-анализ (Ollama)", "status": "active"},
]


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
# NATS
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
            msg = await nats_request_with_trace(nc, subject, data, timeout)
            return json.loads(msg.data.decode())
        except (NatsTimeoutError, asyncio.TimeoutError, Exception) as exc:
            last_error = exc
            logger.warning("Retry %d/%d for %s failed: %s", attempt, retries, subject, exc)
            if attempt < retries:
                await asyncio.sleep(0.3 * attempt)

    raise HTTPException(
        status_code=504,
        detail=f"Агент '{subject}' не ответил после {retries} попыток: {last_error}",
    )


def default_appointment_date() -> str:
    return (datetime.utcnow() + timedelta(days=3)).strftime("%Y-%m-%d")


def feedback_total_from_redis() -> int:
    try:
        val = get_redis().get("total_feedbacks")
        return int(val or 0)
    except Exception:
        return 0


async def run_patient_pipeline(body: PatientRegisterRequest) -> dict:
    task_id = str(uuid.uuid4())
    patient_name = f"{body.first_name} {body.last_name}".strip()
    appointment_date = body.appointment_date or default_appointment_date()

    depth = queue_push()
    try:
        scaled = try_scale_appointment_agents(depth)
        if scaled:
            logger.info("Autoscale triggered at queue depth %d", depth)

        with tracer.start_as_current_span("patient-pipeline") as span:
            span.set_attribute("patient.id", body.patient_id)
            span.set_attribute("queue.depth", depth)

            triage_result = await nats_request(
                "tasks.triage",
                {
                    "id": task_id,
                    "patient": patient_name,
                    "symptoms": body.symptoms,
                    "urgency": body.urgency,
                },
            )

            llm_result = await nats_request(
                "tasks.llm",
                {
                    "id": task_id,
                    "patient": patient_name,
                    "symptoms": body.symptoms,
                },
            )

            auction_winner, auction_bids = await collect_auction_bids(
                nc, task_id, timeout_sec=settings.auction_timeout
            )
            state.last_auction_winner = auction_winner
            state.last_auction_bids = auction_bids

            appointment_result = await nats_request(
                "tasks.appointment",
                {
                    "id": task_id,
                    "patient": patient_name,
                    "date": appointment_date,
                    "specialty": triage_result.get("specialty", "терапевт"),
                    "preferred_agent": auction_winner.get("agent_id"),
                    "agent_cost": auction_winner.get("cost"),
                },
            )

            reminder_result = await nats_request(
                "tasks.reminder",
                {"id": task_id, "patient": patient_name, "date": appointment_date},
            )

            feedback_result = await nats_request(
                "tasks.feedback",
                {"id": task_id, "patient": patient_name, "rating": body.rating},
            )

            state.tasks_processed += 1

            result = {
                "task_id": task_id,
                "patient_id": body.patient_id,
                "patient": patient_name,
                "appointment_date": appointment_date,
                "queue_depth_at_start": depth,
                "auction": {"winner": auction_winner, "bids": auction_bids},
                "triage": triage_result,
                "llm": llm_result,
                "appointment": appointment_result,
                "reminder": reminder_result,
                "feedback": feedback_result,
            }
            state.recent_results.appendleft(
                {
                    "task_id": task_id,
                    "patient": patient_name,
                    "priority": triage_result.get("priority"),
                    "at": datetime.utcnow().isoformat(),
                }
            )
            return result
    finally:
        queue_pop()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def startup():
    global nc
    nc = await nats.connect(settings.nats_url)
    get_redis().ping()
    logger.info("Connected to NATS at %s, Redis OK", settings.nats_url)


@app.on_event("shutdown")
async def shutdown():
    if nc:
        await nc.close()


@app.get("/health")
async def health():
    redis_ok = False
    try:
        get_redis().ping()
        redis_ok = True
    except Exception:
        pass
    return {
        "status": "ok",
        "nats": nc is not None and nc.is_connected,
        "redis": redis_ok,
    }


@app.get("/status")
async def status():
    return {
        "variant": 18,
        "domain": "Система поддержки пациентов",
        "agents": [a["name"] for a in AGENTS_META],
        "tasks_processed": state.tasks_processed,
        "queue_depth": queue_depth(),
        "last_auction_winner": state.last_auction_winner,
        "last_auction_bids": state.last_auction_bids,
        "jaeger_ui": "http://localhost:16686",
        "monitor_ui": "http://localhost:8000/monitor",
    }


def _monitor_context(request: Request) -> dict:
    return {
        "request": request,
        "tasks_processed": state.tasks_processed,
        "queue_depth": queue_depth(),
        "queue_threshold": settings.queue_scale_threshold,
        "nats_ok": nc is not None and nc.is_connected,
        "feedback_total": feedback_total_from_redis(),
        "jaeger_ui": "http://localhost:16686",
        "agents": AGENTS_META,
        "auction_winner": state.last_auction_winner,
        "auction_bids": state.last_auction_bids,
        "autoscale_events": get_autoscale_events(),
        "recent_results": list(state.recent_results),
        "run_error": state.last_run_error,
        "last_run_result": state.last_run_result,
    }


@app.get("/monitor", response_class=HTMLResponse)
async def monitor_page(request: Request):
    state.last_run_error = ""
    return templates.TemplateResponse("monitor.html", _monitor_context(request))


@app.post("/monitor/run")
async def monitor_run(
    request: Request,
    patient_id: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    symptoms: str = Form(...),
    urgency: str = Form("normal"),
    rating: int = Form(5),
):
    body = PatientRegisterRequest(
        patient_id=patient_id,
        first_name=first_name,
        last_name=last_name,
        symptoms=[s.strip() for s in symptoms.split(",") if s.strip()],
        urgency=urgency,
        rating=rating,
    )
    try:
        result = await run_patient_pipeline(body)
        state.last_run_result = json.dumps(result, ensure_ascii=False, indent=2)
        state.last_run_error = ""
        return RedirectResponse(url="/monitor", status_code=303)
    except HTTPException as exc:
        state.last_run_error = str(exc.detail)
        state.last_run_result = ""
        return templates.TemplateResponse("monitor.html", _monitor_context(request))


@app.post("/patients/register")
async def register_patient(body: PatientRegisterRequest):
    logger.info("Register patient_id=%s", body.patient_id)
    try:
        return await run_patient_pipeline(body)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Pipeline error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/process")
async def process_legacy(body: LegacyProcessRequest):
    mapped = PatientRegisterRequest(
        patient_id=str(uuid.uuid4())[:8],
        first_name=body.patient,
        last_name="",
        symptoms=[body.symptoms],
        appointment_date=body.date,
    )
    return await register_patient(mapped)
