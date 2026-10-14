import pytest
from backend.database.crud import init_db
from backend.graph.tools import (
    check_availability,
    create_reservation,
    get_reservation,
    modify_reservation,
    cancel_reservation,
    get_menu,
    get_restaurant_info
)

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db()

def test_tool_restaurant_info():
    res = get_restaurant_info.invoke({"key": "address"})
    assert "Via Toledo" in res

    hours = get_restaurant_info.invoke({"key": "opening_hours"})
    assert "pranzo" in hours.lower()

def test_tool_menu():
    menu_res = get_menu.invoke({"category": "Antipasti"})
    assert "Bruschette" in menu_res or "Tagliere" in menu_res

    gf_menu = get_menu.invoke({"is_gluten_free": True})
    assert len(gf_menu) > 0

def test_tool_reservation_flow():
    # Check availability
    avail = check_availability.invoke({
        "date": "2026-10-21",
        "time": "13:30",
        "guests": 2
    })
    assert "Disponibilità confermata" in avail

    # Create reservation
    book_res = create_reservation.invoke({
        "date": "2026-10-21",
        "time": "13:30",
        "guests": 2,
        "customer_id": "anon_user_tool_test",
        "special_requests": "Tavolo all'aperto"
    })
    assert "Prenotazione confermata con successo" in book_res
    assert "RES-" in book_res

    # Extract code
    import re
    code = re.search(r"RES-[A-Z0-9]+", book_res).group(0)

    # Get reservation
    get_res = get_reservation.invoke({"booking_code": code})
    assert code in get_res
    assert "Attiva" in get_res

    # Modify reservation
    mod_res = modify_reservation.invoke({
        "booking_code": code,
        "new_guests": 4
    })
    assert "aggiornata con successo" in mod_res
    assert "4" in mod_res

    # Cancel reservation
    canc_res = cancel_reservation.invoke({"booking_code": code})
    assert "cancellata correttamente" in canc_res
