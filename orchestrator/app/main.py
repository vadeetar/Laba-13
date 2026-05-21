from fastapi import FastAPI, HTTPException
import nats
import json
import asyncio
from prometheus_client import Counter, make_asgi_app
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

# Настройка Трейсинга (Jaeger)
trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)
otlp_exporter = OTLPSpanExporter(endpoint="http://jaeger:4318/v1/traces")
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(otlp_exporter))

# Метрики
REQUEST_COUNTER = Counter('processed_requests', 'Processed requests count')

app = FastAPI()

# Добавляем метрики Prometheus
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

@app.get('/health')
async def health():
    return {'status': 'ok'}

async def send_with_retry(nc, subject, data, retries=3):
    for attempt in range(retries):
        try:
            with tracer.start_as_current_span(f"attempt_{attempt}"):
                resp = await nc.request(subject, json.dumps(data).encode(), timeout=5)
                return json.loads(resp.data.decode())
        except Exception as e:
            if attempt == retries - 1: raise e
            await asyncio.sleep(1)

@app.post("/patients/register")
async def register_patient(data: dict):
    REQUEST_COUNTER.inc()
    nc = await nats.connect("nats://nats:4222")
    
    with tracer.start_as_current_span("main_request") as span:
        try:
            # 1. Triage с повторами
            triage_data = await send_with_retry(nc, "patients.triage", data)
            
            # 2. Appointment
            app_req = {"patient_id": data["patient_id"], "specialty": triage_data["recommended_specialty"]}
            app_data = await send_with_retry(nc, "appointments.process", app_req)
            
            return {"status": "success", "appointment": app_data, "triage": triage_data}
        except Exception as e:
            span.set_attribute("error", True)
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            await nc.close()
