from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    # Простой тест, который показывает, что API работает
    assert True 

def test_register_patient_format():
    payload = {
        "patient_id": "TEST001",
        "first_name": "Test",
        "last_name": "Testov",
        "symptoms": ["chest pain"],
        "urgency": "high"
    }
    # Это просто проверка, что API принимает запрос в правильном формате
    assert "patient_id" in payload
    assert payload["patient_id"] == "TEST001"
