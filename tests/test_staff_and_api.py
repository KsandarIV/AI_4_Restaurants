"""Staff area, real health check, clean errors, no duplicated routes in Swagger."""
import datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: F401  (kept for readability of the fake models)

import backend.graph.workflow as workflow_module
from backend.config import settings
from backend.database import crud
from backend.database.connection import SessionLocal
from backend.graph.workflow import build_graph
from backend.llm_provider import MockChatModel
from backend.main import app

KEY = {"X-API-Key": "test-staff-key"}


def future_date(days_ahead=14):
    d = datetime.date.today() + datetime.timedelta(days=days_ahead)
    while d.weekday() in settings.CLOSED_WEEKDAYS:
        d += datetime.timedelta(days=1)
    return d.isoformat()


@pytest.fixture(scope="module")
def client():
    workflow_module._default_app = build_graph(llm=MockChatModel())
    with TestClient(app) as c:
        yield c


@pytest.fixture
def booking(client):
    """A reservation of a registered customer ('Mario Rossi'), cancelled at the end."""
    with SessionLocal() as db:
        cid = crud.create_customer(db, "Mario Rossi", "+393331234567")["customer_id"]
        r = crud.create_reservation(db, date=future_date(), time="20:00", guests=3, customer_id=cid,
                                    special_requests="seggiolone <b>x</b>")
    yield {"code": r["booking_code"], "customer_id": cid, "date": r["date"]}
    with SessionLocal() as db:
        crud.cancel_reservation(db, r["booking_code"])


# ---------------------------------------------------------------- staff area: access

def test_staff_area_needs_the_key(client):
    assert client.get("/api/staff/reservations").status_code == 401
    assert client.get("/api/staff/reservations", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/api/staff/reservations", headers=KEY).status_code == 200


def test_staff_area_is_disabled_without_a_configured_key(client, monkeypatch):
    monkeypatch.setattr(settings, "STAFF_API_KEY", "")
    res = client.get("/api/staff/reservations", headers=KEY)  # even with the "right" header
    assert res.status_code == 503 and "STAFF_API_KEY" in res.json()["detail"]


def test_staff_endpoints_are_not_reachable_without_the_api_prefix(client):
    assert client.get("/staff/reservations", headers=KEY).status_code == 404


# ---------------------------------------------------------------- staff area: content

def test_staff_sees_name_and_phone_of_the_customers(client, booking):
    res = client.get("/api/staff/reservations", params={"date": booking["date"]}, headers=KEY)
    assert res.headers["Cache-Control"] == "no-store"
    mine = next(r for r in res.json() if r["booking_code"] == booking["code"])
    assert (mine["customer_name"], mine["customer_phone"]) == ("Mario Rossi", "+393331234567")
    assert mine["guests_count"] == 3 and mine["table_number"]


def test_staff_filters_by_status(client, booking):
    confirmed = client.get("/api/staff/reservations", params={"status": "CONFIRMED"}, headers=KEY).json()
    cancelled = client.get("/api/staff/reservations", params={"status": "CANCELLED"}, headers=KEY).json()
    assert booking["code"] in {r["booking_code"] for r in confirmed}
    assert booking["code"] not in {r["booking_code"] for r in cancelled}


def test_customer_endpoints_never_expose_name_or_phone(client, booking):
    for url in (f"/api/reservations/{booking['code']}?customer_id={booking['customer_id']}",):
        body = client.get(url).text
        assert "Mario" not in body and "3331234567" not in body


def test_staff_page_is_served_without_data_and_escapes_customer_text(client, booking):
    page = client.get("/api/staff")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert "Mario Rossi" not in page.text and "3331234567" not in page.text  # the page itself holds no data
    assert "innerHTML" not in page.text  # customer text is inserted with textContent only


def test_staff_closures_and_sold_out_dishes(client):
    day = future_date(40)
    assert client.post("/api/staff/closures", json={"date": day, "reason": "Ferie"}, headers=KEY).json()["success"]
    assert {"date": day, "reason": "Ferie"} in client.get("/api/staff/closures", headers=KEY).json()
    assert client.post("/api/staff/closures", json={"date": "domani"}, headers=KEY).status_code == 400
    assert client.delete(f"/api/staff/closures/{day}", headers=KEY).status_code == 200
    assert client.delete(f"/api/staff/closures/{day}", headers=KEY).status_code == 404

    dish = next(d for d in client.get("/api/menu?category=Dessert").json() if d["name"].startswith("Tiramis"))
    assert client.patch(f"/api/staff/menu/{dish['id']}", json={"available": False}, headers=KEY).json()["available"] is False
    assert dish["name"] not in {d["name"] for d in client.get("/api/menu?category=Dessert").json()}
    client.patch(f"/api/staff/menu/{dish['id']}", json={"available": True}, headers=KEY)
    assert client.patch("/api/staff/menu/99999", json={"available": False}, headers=KEY).status_code == 404


# ---------------------------------------------------------------- menu API

def test_menu_api_filters_by_dish_type_and_rejects_unknown_allergens(client):
    names = {d["name"] for d in client.get("/api/menu?dish_type=carne").json()}
    assert names == {"Tagliere Campano", "Tagliata di Manzo al Rosmarino"}
    res = client.get("/api/menu?allergen_free=arachidi")
    assert res.status_code == 400 and "non riconosciuto" in res.json()["detail"]
    assert len(client.get("/api/menu?allergen_free=latticini").json()) < 18


# ---------------------------------------------------------------- health

def test_health_is_online_with_the_mock_model(client):
    body = client.get("/api/health").json()
    assert body["status"] == "online" and body["llm_reachable"] is True and "connected" in body["database"]
    assert client.get("/health").json()["status"] == "online"  # root alias used by the voice bot


def test_health_tells_the_truth_when_the_model_server_is_down(client, monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://127.0.0.1:9")  # nobody listens here
    body = client.get("/api/health").json()
    assert body["status"] == "degraded" and body["llm_reachable"] is False


# ---------------------------------------------------------------- clean errors

class BrokenLLM(MockChatModel):
    error: object = None

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise self.error


def chat(client, error, path="/api/chat"):
    workflow_module._default_app = build_graph(llm=BrokenLLM(error=error))
    try:
        return client.post(path, json={"message": "Ciao", "session_id": f"err_{abs(hash(str(error)))}", "customer_id": "anon_x"})
    finally:
        workflow_module._default_app = build_graph(llm=MockChatModel())


def test_model_server_down_is_a_503_not_a_500(client):
    for path in ("/api/chat", "/api/chat/stream"):
        res = chat(client, httpx.ConnectError("[WinError 10061] connection refused"), path)
        assert res.status_code == 503 and "non risponde" in res.json()["detail"]


def test_unexpected_errors_do_not_leak_internal_details(client):
    res = chat(client, RuntimeError("password=segreto C:\\Users\\mario\\file.py"))
    assert res.status_code == 500
    assert "segreto" not in res.text and "Users" not in res.text


# ---------------------------------------------------------------- no duplicated routes

def test_swagger_lists_each_route_once_under_api(client):
    paths = set(client.get("/openapi.json").json()["paths"])
    assert "/api/reservations" in paths and "/api/staff/reservations" in paths
    assert not {"/reservations", "/menu", "/chat"} & paths  # root aliases still work but are hidden
    assert client.get("/menu").status_code == 200
