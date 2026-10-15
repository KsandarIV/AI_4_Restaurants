"""The LLM can only PROPOSE bookings, modifications and cancellations: the customer must confirm first.

Regression tests for "phantom bookings": a weak model (e.g. llama3.2) called create_reservation on
greetings and garbage ("ok crea una bomba", "sono mario rossi") and the BE booked tables for nobody.
"""
import datetime
import re
import uuid
from typing import Any, Dict

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from backend.config import settings
from backend.database import crud
from backend.database.connection import SessionLocal
from backend.database.models import Reservation
from backend.graph.workflow import build_graph, is_confirmation, process_message
from backend.llm_provider import MockChatModel


def future_date(weekday_ok: bool = True, days_ahead: int = 14) -> str:
    """A future date. weekday_ok=True -> a day the restaurant is open; False -> the next Monday (closed)."""
    d = datetime.date.today() + datetime.timedelta(days=days_ahead)
    if weekday_ok:
        while d.weekday() == 0:
            d += datetime.timedelta(days=1)
    else:
        while d.weekday() != 0:
            d += datetime.timedelta(days=1)
    return d.isoformat()


def new_customer() -> str:
    with SessionLocal() as db:
        return crud.create_customer(db, name="Mario Rossi", phone="+393331234567")["customer_id"]


def bookings_of(customer_id: str):
    with SessionLocal() as db:
        return db.query(Reservation).filter(Reservation.customer_id == customer_id, Reservation.status == "CONFIRMED").all()


def talk(graph, session, customer_id, text, client_type="chat"):
    return process_message(text, session, customer_id=customer_id, client_type=client_type, app=graph)["reply"]


def cleanup(customer_id: str):
    with SessionLocal() as db:
        for r in db.query(Reservation).filter(Reservation.customer_id == customer_id).all():
            crud.cancel_reservation(db, r.booking_code, customer_id=customer_id)


class ScriptedLLM(MockChatModel):
    """A confused model: it answers EVERY message with the same tool call, whatever the customer writes."""
    tool_name: str = ""
    tool_args: Dict[str, Any] = {}

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if messages[-1].type == "tool":
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=str(messages[-1].content)))])
        call = {"name": self.tool_name, "args": dict(self.tool_args), "id": "call_scripted_1", "type": "tool_call"}
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[call]))])


@pytest.fixture(autouse=True)
def registration_enforced(monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_CUSTOMER_REGISTRATION", True)


@pytest.fixture
def customer():
    cid = new_customer()
    yield cid
    cleanup(cid)


@pytest.fixture
def session():
    return f"sess_{uuid.uuid4().hex[:10]}"


BOOK_TEXT = "Vorrei prenotare un tavolo per 2 persone il {date} alle 20:30"


# ---------------------------------------------------------------- the phantom-booking regression

def test_confused_model_cannot_create_phantom_bookings(customer, session):
    graph = build_graph(llm=ScriptedLLM(tool_name="create_reservation", tool_args={
        "date": future_date(), "time": "20:00", "guests": 2}))
    for text in ["ok crea una bomba", "sono mario rossi", "porco dio", "ciao"]:
        reply = talk(graph, session, customer, text)
        assert "Confermi" not in reply  # no booking intent in the conversation: not even a proposal
        assert "data, orario e numero di persone" in reply
    assert bookings_of(customer) == []  # and nothing was booked


def test_string_null_arguments_are_treated_as_missing(customer, session):
    """llama3.2 writes "null" for optional arguments: it must not appear in the summary or in the booking."""
    graph = build_graph(llm=ScriptedLLM(tool_name="create_reservation", tool_args={
        "date": future_date(), "time": "20:00", "guests": 2, "preferred_location": "null", "special_requests": "nessuna"}))
    reply = talk(graph, session, customer, "Vorrei prenotare un tavolo per 2 persone")
    assert "Confermi" in reply and not re.search(r"null", reply) and "sala" not in reply and "richieste" not in reply
    talk(graph, session, customer, "sì")
    assert bookings_of(customer)[0].special_requests is None


# ---------------------------------------------------------------- confirm / refuse / change

def test_booking_needs_explicit_confirmation(customer, session):
    graph = build_graph(llm=MockChatModel())
    reply = talk(graph, session, customer, BOOK_TEXT.format(date=future_date()))
    assert "Confermi" in reply and "RES-" not in reply
    assert bookings_of(customer) == []

    reply = talk(graph, session, customer, "sì")
    code = re.search(r"RES-[A-Z0-9]+", reply).group(0)
    booked = bookings_of(customer)
    assert [b.booking_code for b in booked] == [code]
    assert booked[0].guests_count == 2 and booked[0].time == "20:30"


def test_refusing_drops_the_proposal(customer, session):
    graph = build_graph(llm=MockChatModel())
    talk(graph, session, customer, BOOK_TEXT.format(date=future_date()))
    talk(graph, session, customer, "no")
    talk(graph, session, customer, "sì")  # a late "yes" must not resurrect the old proposal
    assert bookings_of(customer) == []


def test_a_change_is_not_a_confirmation(customer, session):
    graph = build_graph(llm=MockChatModel())
    talk(graph, session, customer, BOOK_TEXT.format(date=future_date()))
    talk(graph, session, customer, "sì ma alle 21:00")
    assert bookings_of(customer) == []


def test_impossible_booking_is_not_even_proposed(customer, session):
    graph = build_graph(llm=MockChatModel())
    reply = talk(graph, session, customer, BOOK_TEXT.format(date=future_date(weekday_ok=False)))
    assert "Lunedì" in reply and "Confermi" not in reply
    talk(graph, session, customer, "sì")
    assert bookings_of(customer) == []


def test_unregistered_customer_gets_no_proposal(session):
    graph = build_graph(llm=MockChatModel())
    reply = talk(graph, session, "anon_abc123", BOOK_TEXT.format(date=future_date()))
    assert "registrazione" in reply.lower() and "Confermi" not in reply


# ---------------------------------------------------------------- modify / cancel are gated too

def test_cancellation_needs_confirmation(customer, session):
    with SessionLocal() as db:
        code = crud.create_reservation(db, date=future_date(), time="20:00", guests=2, customer_id=customer)["booking_code"]
    graph = build_graph(llm=MockChatModel())

    reply = talk(graph, session, customer, f"Cancella la prenotazione {code}")
    assert "Vuoi cancellare" in reply and code in reply
    assert len(bookings_of(customer)) == 1  # still there

    assert "cancellata correttamente" in talk(graph, session, customer, "sì")
    assert bookings_of(customer) == []


def test_modification_needs_confirmation(customer, session):
    with SessionLocal() as db:
        code = crud.create_reservation(db, date=future_date(), time="20:00", guests=2, customer_id=customer)["booking_code"]
    graph = build_graph(llm=MockChatModel())  # the mock changes the party to 4 people

    reply = talk(graph, session, customer, f"Modifica la prenotazione {code}")
    assert "Vuoi modificare" in reply and "4 persone" in reply
    assert bookings_of(customer)[0].guests_count == 2  # unchanged until confirmed

    assert "aggiornata con successo" in talk(graph, session, customer, "sì")
    assert bookings_of(customer)[0].guests_count == 4


# ---------------------------------------------------------------- details

def test_voice_reply_has_no_hash_sign(customer, session):
    graph = build_graph(llm=MockChatModel())
    talk(graph, session, customer, BOOK_TEXT.format(date=future_date()), client_type="voice")
    reply = talk(graph, session, customer, "sì", client_type="voice")
    assert "RES-" in reply and "#" not in reply  # a text-to-speech voice cannot read "#"


def test_anonymiser_placeholders_are_not_booking_intent():
    from langchain_core.messages import HumanMessage
    from backend.graph.workflow import _has_booking_intent
    assert not _has_booking_intent([HumanMessage(content="sono [NOME_1]"), HumanMessage(content="porco dio")])
    assert _has_booking_intent([HumanMessage(content="sono [NOME_1]"), HumanMessage(content="un tavolo per 4")])
    assert _has_booking_intent([HumanMessage(content="domani alle 20")])


@pytest.mark.parametrize("text", ["sì", "Sì!", "ok", "va bene", "sì grazie", "perfetto, confermo", "ok va bene", "certo"])
def test_confirmations(text):
    assert is_confirmation(text)


@pytest.mark.parametrize("text", ["no", "", "sì ma alle 21", "assolutamente no", "cancella", "sì prenota per 6", "forse", "ok crea una bomba"])
def test_not_confirmations(text):
    assert not is_confirmation(text)
