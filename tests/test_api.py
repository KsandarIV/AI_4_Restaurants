import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings
from backend.llm_provider import MockChatModel
from backend.graph.workflow import build_graph
import backend.graph.workflow as workflow_module

@pytest.fixture(scope="module")
def client():
    # Inject mock graph for tests to ensure offline reproducibility
    mock_llm = MockChatModel()
    workflow_module._default_app = build_graph(llm=mock_llm)

    with TestClient(app) as c:
        yield c

def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "Trattoria Bella Napoli" in data["restaurant"]

def test_menu_endpoint(client):
    response = client.get("/api/menu?category=Primi")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 3
    assert any("Paccheri" in item["name"] for item in data)

def test_info_endpoint(client):
    response = client.get("/api/info")
    assert response.status_code == 200
    data = response.json()
    assert "address" in data
    assert "opening_hours" in data

def test_direct_reservation_crud(client):
    # 1. Create reservation
    payload = {
        "date": "2026-10-22",
        "time": "20:00",
        "guests": 4,
        "customer_id": "anon_api_test",
        "special_requests": "Tavolo all'aperto",
        "preferred_location": "terrazza"
    }
    res = client.post("/api/reservations", json=payload)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["success"] is True
    booking_code = res_data["booking_code"]

    # 2. Get reservation
    get_res = client.get(f"/api/reservations/{booking_code}")
    assert get_res.status_code == 200
    assert get_res.json()["booking_code"] == booking_code

    # 3. Modify reservation
    mod_res = client.patch(f"/api/reservations/{booking_code}", json={"new_guests": 5})
    assert mod_res.status_code == 200
    assert mod_res.json()["guests_count"] == 5

    # 4. Cancel reservation
    del_res = client.delete(f"/api/reservations/{booking_code}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "CANCELLED"

def test_chat_endpoint_conversation(client):
    payload = {
        "message": "Buongiorno! Vorrei informazioni sugli orari di apertura.",
        "session_id": "api_chat_session_1",
        "client_type": "voice"
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "api_chat_session_1"
    assert data["client_type"] == "voice"
    assert len(data["reply"]) > 0
