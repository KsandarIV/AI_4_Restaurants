"""Customer registration: name/phone stay in the customers table, the LLM only sees the customer_id."""
import datetime
import re

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

import backend.graph.workflow as workflow_module
from backend.config import settings
from backend.database import crud
from backend.database.connection import SessionLocal
from backend.database.models import Customer
from backend.graph.prompts import get_system_prompt
from backend.graph.workflow import build_graph, process_message
from backend.llm_provider import MockChatModel
from backend.main import app


def future_open_date(days_ahead: int = 14) -> str:
    """A date in the future on which the restaurant is open (it is closed on Mondays)."""
    d = datetime.date.today() + datetime.timedelta(days=days_ahead)
    while d.weekday() == 0:
        d += datetime.timedelta(days=1)
    return d.isoformat()


@pytest.fixture(scope="module")
def client():
    workflow_module._default_app = build_graph(llm=MockChatModel())
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def registration_enforced(monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_CUSTOMER_REGISTRATION", True)


def register(client, name="Mario Rossi", phone="+393331234567") -> str:
    res = client.post("/api/customers", json={"name": name, "phone": phone, "consent": True})
    assert res.status_code == 200, res.text
    return res.json()["customer_id"]


def book(client, customer_id, date=None, time="20:00", guests=2):
    return client.post("/api/reservations", json={
        "date": date or future_open_date(), "time": time, "guests": guests, "customer_id": customer_id
    })


# ---------------------------------------------------------------- registration

def test_registration_returns_only_an_anonymous_id(client):
    res = client.post("/api/customers", json={"name": "Anna Verdi", "phone": "+393407654321", "consent": True})
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"customer_id"}
    assert body["customer_id"].startswith("cust_")
    assert "Verdi" not in res.text and "3407654321" not in res.text

    with SessionLocal() as db:  # the data is in the database, and only there
        row = db.query(Customer).filter(Customer.customer_id == body["customer_id"]).one()
        assert (row.name, row.phone) == ("Anna Verdi", "+393407654321")
        assert row.consent_at is not None
        assert "Verdi" not in repr(row)  # never printed by accident


@pytest.mark.parametrize("payload", [
    {"name": "Mario Rossi", "phone": "+393331234567", "consent": False},   # no consent
    {"name": "Mario Rossi", "phone": "+393331234567"},                     # consent missing
    {"name": "Mario Rossi", "phone": "333 1234567", "consent": True},      # not E.164
    {"name": "Mario Rossi", "phone": "+39abc", "consent": True},
    {"name": "   ", "phone": "+393331234567", "consent": True},            # blank name
    {"phone": "+393331234567", "consent": True},                           # name missing
])
def test_registration_rejects_invalid_data(client, payload):
    assert client.post("/api/customers", json=payload).status_code == 422


def test_each_registration_gets_a_new_id(client):
    assert register(client) != register(client)


# ---------------------------------------------------------------- booking needs registration

def test_booking_rejected_for_unregistered_customer(client):
    res = book(client, "anon_not_registered")
    assert res.status_code == 400
    assert "registrazione" in res.json()["detail"].lower()

    with SessionLocal() as db:
        out = crud.create_reservation(db, date=future_open_date(), time="20:00", guests=2, customer_id="anon_x")
        assert out["success"] is False and "registrazione" in out["error"].lower()


def test_booking_accepted_for_registered_customer(client):
    cid = register(client)
    res = book(client, cid)
    assert res.status_code == 200
    assert res.json()["success"] is True
    client.delete(f"/api/reservations/{res.json()['booking_code']}", params={"customer_id": cid})


def test_name_field_is_never_used_as_customer_id(client, monkeypatch):
    payload = {"date": future_open_date(), "time": "20:00", "guests": 2, "name": "Mario Rossi"}
    # registration on: the name does not identify anybody, so the booking is refused
    assert client.post("/api/reservations", json=payload).status_code == 400
    # registration off (legacy): booking works, but the name is NOT stored as customer_id
    monkeypatch.setattr(settings, "REQUIRE_CUSTOMER_REGISTRATION", False)
    res = client.post("/api/reservations", json=payload)
    assert res.status_code == 200
    with SessionLocal() as db:
        saved = crud.get_reservation(db, res.json()["booking_code"])
        assert saved["customer_id"] == "anon_client"
        crud.cancel_reservation(db, saved["booking_code"])


# ---------------------------------------------------------------- only the owner can touch a booking

def test_only_the_owner_can_read_modify_cancel(client):
    owner, stranger = register(client), register(client, name="Luca Bianchi", phone="+393339998877")
    code = book(client, owner).json()["booking_code"]
    url = f"/api/reservations/{code}"

    # a stranger (or nobody) gets "not found", exactly like for a code that does not exist
    for cid in (stranger, None):
        params = {"customer_id": cid} if cid else {}
        assert client.get(url, params=params).status_code == 404
        assert client.patch(url, json={"new_guests": 4, "customer_id": cid}).status_code == 400
        assert client.delete(url, params=params).status_code == 404

    # ...and nothing changed
    still = client.get(url, params={"customer_id": owner})
    assert still.status_code == 200
    assert still.json()["guests_count"] == 2 and still.json()["status"] == "CONFIRMED"

    # the owner can do everything
    assert client.patch(url, json={"new_guests": 3, "customer_id": owner}).json()["guests_count"] == 3
    assert client.delete(url, params={"customer_id": owner}).json()["status"] == "CANCELLED"


def test_legacy_mode_has_no_ownership_check(client, monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_CUSTOMER_REGISTRATION", False)
    with SessionLocal() as db:
        code = crud.create_reservation(db, date=future_open_date(), time="20:00", guests=2, customer_id="legacy")["booking_code"]
        assert crud.get_reservation(db, code) is not None
        assert crud.cancel_reservation(db, code)["success"] is True


# ---------------------------------------------------------------- through the LLM

def test_conversation_books_for_registered_and_refuses_for_anonymous(client):
    cid, date = register(client), future_open_date()
    app_graph = build_graph(llm=MockChatModel())
    message = f"Vorrei prenotare un tavolo per 2 persone il {date} alle 20:30"

    reply = process_message(message, "sess_reg_1", customer_id=cid, client_type="chat", app=app_graph)["reply"]
    assert "Confermi" in reply and "RES-" not in reply  # proposal first: nothing is booked yet
    reply = process_message("sì", "sess_reg_1", customer_id=cid, client_type="chat", app=app_graph)["reply"]
    code = re.search(r"RES-[A-Z0-9]+", reply).group(0)
    with SessionLocal() as db:
        assert crud.get_reservation(db, code, customer_id=cid)["customer_id"] == cid

    reply = process_message(message, "sess_anon_1", customer_id="anon_abc123", client_type="chat", app=app_graph)["reply"]
    assert "registrazione" in reply.lower() and "RES-" not in reply

    proposal = process_message(f"Cancella la prenotazione {code}", "sess_reg_1", customer_id=cid, client_type="chat", app=app_graph)
    assert "Vuoi cancellare" in proposal["reply"]
    done = process_message("sì", "sess_reg_1", customer_id=cid, client_type="chat", app=app_graph)
    assert "cancellata correttamente" in done["reply"]


class HostileLLM(MockChatModel):
    """Simulates an LLM (or a prompt injection) that tries to cancel someone else's booking."""
    victim_id: str = ""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if messages[-1].type == "tool":
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=str(messages[-1].content)))])
        code = re.search(r"RES-[A-Z0-9]+", str(messages[-1].content)).group(0)
        call = {"name": "cancel_reservation", "args": {"booking_code": code, "customer_id": self.victim_id},
                "id": "call_hostile_1", "type": "tool_call"}
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[call]))])


def test_customer_id_comes_from_the_session_not_from_the_llm(client):
    owner, attacker = register(client), register(client, name="Luca Bianchi", phone="+393339998877")
    code = book(client, owner).json()["booking_code"]

    # the (hostile) LLM claims to act as the owner, but the session says "attacker"
    graph = build_graph(llm=HostileLLM(victim_id=owner))
    reply = process_message(f"Cancella {code}", "sess_hostile_1", customer_id=attacker, client_type="chat", app=graph)["reply"]
    assert "non trovo" in reply.lower()  # not even proposed: the session's customer does not own it

    with SessionLocal() as db:
        assert crud.get_reservation(db, code, customer_id=owner)["status"] == "CONFIRMED"
        crud.cancel_reservation(db, code, customer_id=owner)


# ---------------------------------------------------------------- prompt

def test_prompt_warns_about_unregistered_customers_only():
    assert "NON è registrato" in get_system_prompt(customer_id="anon_abc123")
    assert "NON è registrato" not in get_system_prompt(customer_id="cust_8f3a1c9d2b4e")
