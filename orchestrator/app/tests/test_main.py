import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app, choose_appointment_agent


client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_auction_picks_lowest_cost():
    winner = choose_appointment_agent()
    assert winner["name"] == "appointment-agent-2"
    assert winner["cost"] == 1


def test_register_patient_format():
    payload = {
        "patient_id": "PAT001",
        "first_name": "Иван",
        "last_name": "Петров",
        "symptoms": ["chest pain"],
        "urgency": "high",
    }
    assert payload["patient_id"] == "PAT001"
    assert "chest pain" in payload["symptoms"]


@pytest.mark.asyncio
async def test_nats_request_retry_success():
    from app.main import nats_request

    mock_nc = MagicMock()
    mock_msg = MagicMock()
    mock_msg.data = json.dumps({"status": "ok"}).encode()

    mock_nc.request = AsyncMock(side_effect=[Exception("fail"), mock_msg])

    with patch("app.main.nc", mock_nc):
        result = await nats_request("tasks.triage", {"id": "1"}, retries=2)
    assert result["status"] == "ok"
    assert mock_nc.request.await_count == 2
