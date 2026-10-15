"""Allergies and intolerances are answered by code from the menu: the LLM must never improvise on them."""
import datetime
import uuid

import pytest

from backend.config import settings
from backend.database import crud
from backend.database.connection import SessionLocal
from backend.graph.allergies import answer_allergy_question
from backend.graph.workflow import build_graph, process_message
from backend.llm_provider import MockChatModel


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    crud.init_db()


def dishes_in(reply):
    from backend.database.models import MenuItem
    with SessionLocal() as db:
        return {m.name for m in db.query(MenuItem).all() if m.name in reply}


# ---------------------------------------------------------------- what is answered, and with what

def test_celiac_gets_only_gluten_free_dishes():
    reply = answer_allergy_question("sono celiaco, che primi avete?")
    assert "senza glutine" in reply
    assert "Risotto ai Funghi Porcini" in dishes_in(reply)
    assert not {"Spaghetti alle Vongole Veraci", "Paccheri alla Sorrentina", "Tiramisù Artigianale"} & dishes_in(reply)


def test_lactose_intolerance_with_a_synonym():
    reply = answer_allergy_question("ho un'intolleranza ai latticini, cosa posso mangiare come antipasto?")
    assert "Polpo alla Luciana" in dishes_in(reply)
    assert not {"Tagliere Campano", "Tiramisù Artigianale", "Paccheri alla Sorrentina"} & dishes_in(reply)


def test_several_allergens_at_once():
    reply = answer_allergy_question("sono allergico al pesce e ai molluschi")
    assert not {"Polpo alla Luciana", "Filetto di Orata all'Acqua Pazza", "Spaghetti alle Vongole Veraci"} & dishes_in(reply)
    assert "Tagliata di Manzo al Rosmarino" in dishes_in(reply)


def test_an_allergen_not_in_the_menu_gets_no_invented_list():
    reply = answer_allergy_question("sono allergico alle arachidi, cosa mi consigliate?")
    assert "non ho informazioni" in reply.lower() and "personale di sala" in reply
    assert dishes_in(reply) == set()  # no dish is called "safe"
    assert "glutine" in reply and "lattosio" in reply  # what the menu does track


def test_every_answer_tells_to_warn_the_staff():
    assert "personale di sala" in answer_allergy_question("sono celiaco")


def test_voice_gets_a_sentence_not_a_list():
    reply = answer_allergy_question("sono celiaco", client_type="voice")
    assert reply.startswith("Senza glutine abbiamo:") and "\n" not in reply and "€" not in reply


@pytest.mark.parametrize("text", [
    "Avete piatti di pesce?", "ciao", "cosa c'è di nuovo nel menu?", "Che dessert avete?",
    "Vorrei prenotare un tavolo per 4, uno di noi è celiaco",   # a booking: the LLM puts it in the special requests
    "Prenotazione per 2 persone, siamo intolleranti al lattosio",
])
def test_other_messages_are_left_to_the_llm(text):
    assert answer_allergy_question(text) is None


# ---------------------------------------------------------------- in the conversation

class ForbiddenLLM(MockChatModel):
    """Fails the test if the language model is ever asked: allergies must not reach it."""
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise AssertionError("l'LLM non deve rispondere alle domande sulle allergie")


def test_allergy_question_never_reaches_the_llm_and_is_remembered():
    graph = build_graph(llm=ForbiddenLLM())
    session = f"allergy_{uuid.uuid4().hex[:8]}"
    out = process_message("sono celiaco, cosa posso mangiare?", session, customer_id="anon_a", app=graph)
    assert "Risotto ai Funghi Porcini" in out["reply"]
    stored = graph.get_state({"configurable": {"thread_id": session}}).values["messages"]
    assert [m.type for m in stored] == ["human", "ai"]  # the exchange is part of the conversation


def test_an_allergy_question_drops_a_pending_booking_proposal():
    graph = build_graph(llm=MockChatModel())
    session = f"allergy_{uuid.uuid4().hex[:8]}"
    day = datetime.date.today() + datetime.timedelta(days=14)
    while day.weekday() in settings.CLOSED_WEEKDAYS:
        day += datetime.timedelta(days=1)
    with SessionLocal() as db:
        cid = crud.create_customer(db, "Mario Rossi", "+393331234567")["customer_id"]
    proposal = process_message(f"Vorrei prenotare un tavolo per 2 persone il {day} alle 20:30", session, customer_id=cid, app=graph)["reply"]
    assert "Confermi" in proposal
    process_message("sono allergico alle uova", session, customer_id=cid, app=graph)
    reply = process_message("sì", session, customer_id=cid, app=graph)["reply"]  # a late yes must not book
    assert "RES-" not in reply
