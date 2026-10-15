import pytest
import datetime
from backend.database.connection import SessionLocal
from backend.database import crud
from backend.graph.prompts import get_system_prompt
from backend.graph.workflow import build_graph, process_message
from backend.llm_provider import MockChatModel

@pytest.fixture(scope="module", autouse=True)
def init():
    crud.init_db()

def test_past_date_rejected():
    with SessionLocal() as db:
        res = crud.create_reservation(
            db=db,
            date="2020-01-01",
            time="13:00",
            guests=2,
            customer_id="test_past"
        )
        assert res["success"] is False
        assert "passata" in res["error"].lower()

def test_invalid_date_format_rejected():
    with SessionLocal() as db:
        res1 = crud.create_reservation(
            db=db,
            date="domani",
            time="13:00",
            guests=2,
            customer_id="test_format"
        )
        assert res1["success"] is False
        assert "formato" in res1["error"].lower()

        res2 = crud.create_reservation(
            db=db,
            date="2026/10/20",
            time="13:00",
            guests=2,
            customer_id="test_format"
        )
        assert res2["success"] is False

def test_out_of_hours_rejected():
    with SessionLocal() as db:
        # 11:00 is before lunch opens at 12:00
        res1 = crud.create_reservation(
            db=db,
            date="2026-10-21",
            time="11:00",
            guests=2,
            customer_id="test_hours"
        )
        assert res1["success"] is False
        assert "fuori servizio" in res1["error"].lower()

        # 18:00 is before dinner opens at 19:00
        res2 = crud.create_reservation(
            db=db,
            date="2026-10-21",
            time="18:00",
            guests=2,
            customer_id="test_hours"
        )
        assert res2["success"] is False
        assert "fuori servizio" in res2["error"].lower()

        # 23:45 is after dinner closes at 23:30 (and last booking at 22:00)
        res3 = crud.create_reservation(
            db=db,
            date="2026-10-21",
            time="23:45",
            guests=2,
            customer_id="test_hours"
        )
        assert res3["success"] is False
        assert "fuori servizio" in res3["error"].lower()

def test_table_turnover_90_minutes():
    """
    Test that a table is occupied for 90 minutes,
    so another booking for the same table overlaps at +30m but succeeds at +90m.
    Table 12 is the only 10-person table in seed_data.
    """
    target_date = "2026-10-25"  # Sunday
    created_codes = []
    with SessionLocal() as db:
        try:
            # Clean any leftover from previous runs for this date
            db.query(crud.Reservation).filter(crud.Reservation.date == target_date).delete()
            db.commit()

            # 1. First booking: 10 people at 19:30 (occupies Table 12 from 19:30 to 21:00)
            res1 = crud.create_reservation(
                db=db,
                date=target_date,
                time="19:30",
                guests=10,
                customer_id="turnover_group_1"
            )
            assert res1["success"] is True
            assert res1["table_number"] == 12
            created_codes.append(res1["booking_code"])

            # 2. Second booking at 20:00 for 10 people (within the 90 min window: 19:30-21:00)
            # Must FAIL because Table 12 is busy and there are no other 10-person tables!
            res2 = crud.create_reservation(
                db=db,
                date=target_date,
                time="20:00",
                guests=10,
                customer_id="turnover_group_2"
            )
            assert res2["success"] is False
            assert "non ci sono tavoli disponibili" in res2["error"].lower()

            # 3. Third booking at 21:00 for 10 people (after 90 minutes)
            # Must SUCCEED because Table 12 has freed up!
            res3 = crud.create_reservation(
                db=db,
                date=target_date,
                time="21:00",
                guests=10,
                customer_id="turnover_group_3"
            )
            assert res3["success"] is True
            assert res3["table_number"] == 12
            created_codes.append(res3["booking_code"])
        finally:
            for c in created_codes:
                crud.cancel_reservation(db, c)

def test_customer_id_reaches_reservation():
    """
    Verify customer_id passes through LangGraph and is saved on the reservation in SQLite.
    """
    with SessionLocal() as db:
        db.query(crud.Reservation).filter(crud.Reservation.date == "2026-10-21").delete()
        db.commit()

    mock_llm = MockChatModel()
    app = build_graph(llm=mock_llm)

    custom_cid = "client_special_888"
    session_id = "sess_cid_test_1"

    res = process_message(
        message="Vorrei prenotare un tavolo per 2 persone il 2026-10-21 alle 20:30",
        session_id=session_id,
        customer_id=custom_cid,
        client_type="chat",
        app=app
    )
    assert res["customer_id"] == custom_cid
    assert "Confermi" in res["reply"]  # the LLM only proposes; the customer must confirm

    res = process_message(
        message="sì",
        session_id=session_id,
        customer_id=custom_cid,
        client_type="chat",
        app=app
    )
    assert res["customer_id"] == custom_cid

    # Verify in DB
    import re
    match = re.search(r"RES-[A-Z0-9]+", res["reply"])
    assert match is not None
    code = match.group(0)

    with SessionLocal() as db:
        booking = crud.get_reservation(db, code)
        assert booking is not None
        assert booking["customer_id"] == custom_cid

def test_voice_prompt_differentiation():
    """
    Verify that get_system_prompt produces different instructions for voice vs chat.
    """
    prompt_voice = get_system_prompt(client_type="voice", customer_id="user_v1")
    prompt_chat = get_system_prompt(client_type="chat", customer_id="user_c1")

    assert "MODALITÀ BOT VOCALE ATTIVA" in prompt_voice
    assert "SINTESI VOCALE" in prompt_voice
    assert "MODALITÀ CHAT TESTUALE ATTIVA" in prompt_chat
    assert "user_v1" in prompt_voice
    assert "user_c1" in prompt_chat
