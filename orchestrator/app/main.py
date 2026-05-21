from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import nats
import json
import uuid
import asyncio
from datetime import datetime
from app.config import settings

app = FastAPI(title="Оркестратор: Система поддержки пациентов")
nc = nats.NATS()


# --- СХЕМЫ ДАННЫХ ---
class AppointmentRequest(BaseModel):
    patient_id: str
    doctor_specialty: str
    preferred_time: datetime


class FeedbackRequest(BaseModel):
    patient_id: str
    rating: int
    comments: str


# --- СТАРТ И СТОП СЕРВЕРА ---
@app.on_event("startup")
async def startup():
    await nc.connect(settings.nats_url)
    print("✅ Оркестратор подключен к NATS")


@app.on_event("shutdown")
async def shutdown():
    await nc.close()


# --- МЕТОД 1: ЗАПИСЬ К ВРАЧУ (PIPELINE) ---
@app.post("/appointments/")
async def create_appointment_pipeline(request: AppointmentRequest):
    task_id = str(uuid.uuid4())
    task_payload = request.model_dump_json()
    appointment_task = {"id": task_id, "type": "appointment", "payload": task_payload}

    try:
        msg1 = await nc.request("tasks.appointment", json.dumps(appointment_task).encode(), timeout=5.0)
        result1 = json.loads(msg1.data.decode())

        if not result1.get("success"):
            return {"status": "error", "message": "Не удалось создать запись"}

        reminder_task = {"id": task_id, "type": "reminder", "payload": json.dumps(result1)}
        msg2 = await nc.request("tasks.reminder", json.dumps(reminder_task).encode(), timeout=5.0)
        result2 = json.loads(msg2.data.decode())

        return {
            "status": "success",
            "pipeline_results": {
                "step_1_appointment": result1["output"],
                "step_2_reminder": result2["output"]
            }
        }
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Один из агентов цепочки не ответил вовремя")


# --- МЕТОД 2: СБОР ОТЗЫВОВ (С СОХРАНЕНИЕМ СОСТОЯНИЯ) ---
@app.post("/feedback/")
async def collect_feedback(request: FeedbackRequest):
    task_id = str(uuid.uuid4())

    task = {
        "id": task_id,
        "type": "feedback",
        "payload": request.model_dump_json()
    }

    try:
        msg = await nc.request("tasks.feedback", json.dumps(task).encode(), timeout=5.0)
        result = json.loads(msg.data.decode())
        return {"status": "success", "agent_response": result}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Go-агент 'Сбор обратной связи' не отвечает")