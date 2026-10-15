import pytest
from backend.database.crud import init_db
from backend.llm_provider import MockChatModel
from backend.graph.workflow import build_graph, process_message

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db()

def test_graph_greeting():
    mock_llm = MockChatModel()
    app = build_graph(llm=mock_llm)

    res = process_message(
        message="Ciao!",
        session_id="test_sess_1",
        client_type="chat",
        app=app
    )
    assert res["reply"] != ""
    assert "Trattoria Bella Napoli" in res["reply"]

def test_graph_menu_query():
    mock_llm = MockChatModel()
    app = build_graph(llm=mock_llm)

    res = process_message(
        message="Potete dirmi quali sono i primi piatti del menu?",
        session_id="test_sess_2",
        client_type="chat",
        app=app
    )
    assert res["reply"] != ""
    assert ("Paccheri" in res["reply"] or "Spaghetti" in res["reply"] or "Risotto" in res["reply"])

def test_graph_info_query():
    mock_llm = MockChatModel()
    app = build_graph(llm=mock_llm)

    res = process_message(
        message="Quali sono i vostri orari di apertura?",
        session_id="test_sess_3",
        client_type="voice",
        app=app
    )
    assert res["reply"] != ""
    assert "pranzo" in res["reply"].lower()

def test_graph_booking_flow():
    from backend.database.connection import SessionLocal
    from backend.database import crud
    with SessionLocal() as db:
        db.query(crud.Reservation).filter(crud.Reservation.date == "2026-10-21").delete()
        db.commit()

    mock_llm = MockChatModel()
    app = build_graph(llm=mock_llm)

    res = process_message(
        message="Vorrei prenotare un tavolo per 2 persone per il 2026-10-21 alle 20:30",
        session_id="test_sess_4",
        customer_id="anon_client_test",
        client_type="chat",
        app=app
    )
    assert res["reply"] != ""
    # the LLM only proposes: nothing is booked until the customer confirms
    assert "RES-" not in res["reply"] and "Confermi" in res["reply"]

    res = process_message(
        message="sì",
        session_id="test_sess_4",
        customer_id="anon_client_test",
        client_type="chat",
        app=app
    )
    assert "RES-" in res["reply"] and "confermata" in res["reply"].lower()
