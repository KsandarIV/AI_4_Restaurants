import pytest
from backend.database.connection import SessionLocal
from backend.database.crud import (
    init_db,
    create_reservation,
    get_reservation,
    modify_reservation,
    cancel_reservation,
    get_menu_items,
    get_restaurant_info,
    get_available_tables
)

@pytest.fixture(scope="module", autouse=True)
def setup_database():
    init_db()

def test_database_seed():
    with SessionLocal() as db:
        menu = get_menu_items(db)
        assert len(menu) > 0

        info = get_restaurant_info(db)
        assert "address" in info
        assert "phone" in info

def test_reservation_lifecycle():
    with SessionLocal() as db:
        # 1. Create reservation (Martedì or Domenica, e.g. 2026-10-20 is a Tuesday)
        test_date = "2026-10-20"  # Tuesday
        test_time = "20:00"
        guests = 4
        customer_id = "anon_user_123"

        res = create_reservation(
            db=db,
            date=test_date,
            time=test_time,
            guests=guests,
            customer_id=customer_id,
            special_requests="Tavolo tranquillo"
        )
        assert res["success"] is True
        booking_code = res["booking_code"]
        assert booking_code.startswith("RES-")
        assert res["guests_count"] == 4
        assert res["status"] == "CONFIRMED"

        # 2. Retrieve reservation
        fetched = get_reservation(db, booking_code)
        assert fetched is not None
        assert fetched["booking_code"] == booking_code
        assert fetched["customer_id"] == customer_id

        # 3. Modify reservation (change to 6 guests at 20:30)
        mod = modify_reservation(
            db=db,
            booking_code=booking_code,
            new_guests=6,
            new_time="20:30",
            new_requests="Seggiolone per bambino"
        )
        assert mod["success"] is True
        assert mod["guests_count"] == 6
        assert mod["time"] == "20:30"
        assert mod["special_requests"] == "Seggiolone per bambino"

        # 4. Cancel reservation
        canc = cancel_reservation(db, booking_code)
        assert canc["success"] is True
        assert canc["status"] == "CANCELLED"

        # 5. Verify status is CANCELLED
        rechecked = get_reservation(db, booking_code)
        assert rechecked["status"] == "CANCELLED"

def test_closed_on_monday():
    with SessionLocal() as db:
        # 2026-10-19 is a Monday
        res = create_reservation(
            db=db,
            date="2026-10-19",
            time="13:00",
            guests=2,
            customer_id="anon_user_456"
        )
        assert res["success"] is False
        assert "Lunedì" in res["error"]

def test_menu_query():
    with SessionLocal() as db:
        primi = get_menu_items(db, category="Primi")
        assert len(primi) >= 3

        gf_items = get_menu_items(db, is_gluten_free=True)
        assert len(gf_items) > 0
        for item in gf_items:
            assert item["is_gluten_free"] is True
