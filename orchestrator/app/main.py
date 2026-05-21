import asyncio
import json
import uuid
import os

from fastapi import FastAPI

import nats

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

# =========================
# OpenTelemetry
# =========================

trace.set_tracer_provider(TracerProvider())

tracer = trace.get_tracer(__name__)

processor = BatchSpanProcessor(
    OTLPSpanExporter(
        endpoint="http://jaeger:4318/v1/traces"
    )
)

trace.get_tracer_provider().add_span_processor(processor)

# =========================
# FastAPI
# =========================

app = FastAPI()

# =========================
# NATS
# =========================

NATS_URL = os.getenv(
    "NATS_URL",
    "nats://nats:4222"
)

nc = None

# =========================
# Auction Model
# =========================

def choose_agent():

    agents = [
        {"name": "appointment-agent", "cost": 3},
        {"name": "appointment-agent-2", "cost": 1},
    ]

    best = min(
        agents,
        key=lambda x: x["cost"]
    )

    return best

# =========================
# Startup
# =========================

@app.on_event("startup")
async def startup():

    global nc

    nc = await nats.connect(NATS_URL)

    print("Connected to NATS")

# =========================
# Healthcheck
# =========================

@app.get("/health")
async def health():

    return {
        "status": "ok"
    }

# =========================
# Autoscaling Mock
# =========================

def autoscaling_check():

    queue_size = 15

    if queue_size > 10:
        print("Launching additional agent...")

# =========================
# Main Pipeline
# =========================

@app.post("/process")

async def process(data: dict):

    with tracer.start_as_current_span("pipeline"):

        autoscaling_check()

        best_agent = choose_agent()

        print("Chosen agent:", best_agent)

        task_id = str(uuid.uuid4())

        # =========================
        # TRIAGE
        # =========================

        triage_payload = {
            "id": task_id,
            "patient": data["patient"],
            "symptoms": data["symptoms"]
        }

        response = await nc.request(
            "tasks.triage",
            json.dumps(triage_payload).encode(),
            timeout=5
        )

        triage_result = json.loads(
            response.data.decode()
        )

        # =========================
        # APPOINTMENT
        # =========================

        appointment_payload = {
            "id": task_id,
            "patient": data["patient"],
            "date": data["date"]
        }

        response = await nc.request(
            "tasks.appointment",
            json.dumps(appointment_payload).encode(),
            timeout=5
        )

        appointment_result = json.loads(
            response.data.decode()
        )

        # =========================
        # REMINDER
        # =========================

        reminder_payload = {
            "patient": data["patient"],
            "date": data["date"]
        }

        response = await nc.request(
            "tasks.reminder",
            json.dumps(reminder_payload).encode(),
            timeout=5
        )

        reminder_result = json.loads(
            response.data.decode()
        )

        # =========================
        # FEEDBACK
        # =========================

        feedback_payload = {
            "patient": data["patient"],
            "rating": 5
        }

        response = await nc.request(
            "tasks.feedback",
            json.dumps(feedback_payload).encode(),
            timeout=5
        )

        feedback_result = json.loads(
            response.data.decode()
        )

        return {
            "task_id": task_id,
            "triage": triage_result,
            "appointment": appointment_result,
            "reminder": reminder_result,
            "feedback": feedback_result
        }