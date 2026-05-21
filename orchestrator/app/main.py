import os, json, asyncio
from fastapi import FastAPI
from nats.aio.client import Client as NATS
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Инициализация Jaeger
trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)
exporter = OTLPSpanExporter(endpoint="http://jaeger:4318/v1/traces")
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(exporter))

app = FastAPI()


# Логика аукциона
def auction_select(bids):
    # bids - список ответов от агентов с latency
    return min(bids, key=lambda x: x['latency'])


@app.post("/register")
async def register(data: dict):
    with tracer.start_as_current_span("orchestrator_request"):
        nc = await NATS().connect(os.getenv("NATS_URL", "nats://nats:4222"))

        # Пример вызова Triage через аукцион (заглушка)
        # В реальности ты бы слал запрос всем и ждал самый быстрый ответ
        resp = await nc.request("patients.triage", json.dumps(data).encode(), timeout=2)

        await nc.close()
        return json.loads(resp.data.decode())