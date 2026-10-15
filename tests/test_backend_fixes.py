"""Database and booking fixes found while reviewing the backend (allergens, hours, groups, modify...)."""
import datetime

import pytest
from sqlalchemy import create_engine, text

from backend.config import settings
from backend.database import crud
from backend.database.connection import SessionLocal
from backend.database.models import Customer, MenuItem, Reservation, RestaurantInfo
from backend.database.seed_data import opening_hours_text
from backend.graph.prompts import get_system_prompt
from backend.graph.tools import get_menu, get_restaurant_info


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    crud.init_db()


def future_date(days_ahead=14, open_day=True):
    d = datetime.date.today() + datetime.timedelta(days=days_ahead)
    while (d.weekday() in settings.CLOSED_WEEKDAYS) == open_day:
        d += datetime.timedelta(days=1)
    return d.isoformat()


def book(db, cid, **kw):
    kw.setdefault("date", future_date())
    kw.setdefault("time", "20:00")
    kw.setdefault("guests", 2)
    return crud.create_reservation(db, customer_id=cid, **kw)


# ---------------------------------------------------------------- allergens (safety)

@pytest.mark.parametrize("word", ["lattosio", "latticini", "latte", "Formaggi"])
def test_milk_synonyms_all_exclude_the_dishes_with_lactose(word):
    with SessionLocal() as db:
        names = {i["name"] for i in crud.get_menu_items(db, allergen_free=word)}
    assert "Tiramisù Artigianale" not in names and "Paccheri alla Sorrentina" not in names
    assert "Polpo alla Luciana" in names  # contains no lactose


def test_unknown_allergen_is_not_answered_with_the_whole_menu():
    with SessionLocal() as db:
        with pytest.raises(crud.UnknownAllergen) as e:
            crud.get_menu_items(db, allergen_free="arachidi")
    assert "lattosio" in str(e.value) and "glutine" in str(e.value)
    reply = get_menu.invoke({"allergen_free": "arachidi"})
    assert "non riconosciuto" in reply and "Tagliere" not in reply


# ---------------------------------------------------------------- hours and information

def test_what_the_bot_says_about_hours_is_what_the_booking_accepts():
    with SessionLocal() as db:
        text_hours = crud.get_restaurant_info(db, "opening_hours")["opening_hours"]
        assert text_hours == opening_hours_text()
        assert settings.DINNER_START in text_hours and settings.LUNCH_LAST_BOOKING in text_hours
        r = book(db, "hours_test", time=settings.DINNER_START)
        assert r["success"] is True  # the first dinner time announced is bookable
        crud.cancel_reservation(db, r["booking_code"])


@pytest.mark.parametrize("word,expected", [("orari", "Pranzo"), ("indirizzo", "Via Toledo"), ("telefono", "+39"),
                                           ("opening hours", "Pranzo"), ("parcheggio", "Garage")])
def test_information_keys_in_natural_words(word, expected):
    assert expected in get_restaurant_info.invoke({"key": word})


def test_prompt_says_the_weekday_in_italian_and_the_closing_day_from_settings():
    prompt = get_system_prompt(current_date_str="2026-10-15")
    assert "Oggi è Giovedì" in prompt and "Thursday" not in prompt
    assert "CHIUSO ogni settimana: Lunedì" in prompt


def test_prompt_forbids_improvising_on_allergies():
    prompt = get_system_prompt()
    assert "ALLERGIE E INTOLLERANZE" in prompt and "Non suggerire MAI di togliere ingredienti" in prompt


# ---------------------------------------------------------------- bookings

def test_group_bigger_than_the_biggest_table_gets_the_phone_number():
    with SessionLocal() as db:
        r = book(db, "group_test", guests=12)
    assert r["success"] is False
    assert "10 posti" in r["error"] and "+39 081" in r["error"]


def test_modify_keeps_the_room_and_the_table_when_possible():
    with SessionLocal() as db:
        r = book(db, "modify_test", preferred_location="terrazza")
        assert r["table_location"] == "terrazza"
        m = crud.modify_reservation(db, r["booking_code"], new_time="20:30")
        assert m["success"] and m["table_number"] == r["table_number"]
        crud.cancel_reservation(db, r["booking_code"])


def test_times_are_stored_always_the_same_way():
    with SessionLocal() as db:
        r = book(db, "time_test", time="20:5")
        assert r["time"] == "20:05"
        m = crud.modify_reservation(db, r["booking_code"], new_time="21:0")
        assert m["time"] == "21:00"
        crud.cancel_reservation(db, r["booking_code"])


def test_booking_code_collision_is_retried(monkeypatch):
    with SessionLocal() as db:
        first = book(db, "code_test")
        taken = first["booking_code"][4:]
        answers = iter([list(taken), list("ZZZZZZ")])  # first draw collides, the second is free
        monkeypatch.setattr(crud.random, "choices", lambda *a, **k: next(answers))
        assert crud.generate_booking_code(db) == "RES-ZZZZZZ"
        crud.cancel_reservation(db, first["booking_code"])


def test_special_requests_are_trimmed_and_capped():
    with SessionLocal() as db:
        r = book(db, "text_test", special_requests="  " + "x" * 1000)
        assert len(r["special_requests"]) == 300
        m = crud.modify_reservation(db, r["booking_code"], new_requests="   ")
        assert m["special_requests"] is None
        crud.cancel_reservation(db, r["booking_code"])


# ---------------------------------------------------------------- closures and weekly closing day

def test_closure_blocks_booking_with_the_reason_and_can_be_removed():
    day = future_date(days_ahead=30)
    with SessionLocal() as db:
        crud.add_closure(db, day, "Ferragosto")
        r = book(db, "closure_test", date=day)
        assert r["success"] is False and "Ferragosto" in r["error"]
        assert crud.remove_closure(db, day) is True
        r = book(db, "closure_test", date=day)
        assert r["success"] is True
        crud.cancel_reservation(db, r["booking_code"])


def test_adding_a_closure_lists_the_reservations_to_handle():
    day = future_date(days_ahead=31)
    with SessionLocal() as db:
        r = book(db, "closure_test2", date=day)
        out = crud.add_closure(db, day, "Evento privato")
        assert r["booking_code"] in out["reservations_to_handle"]  # not cancelled silently
        crud.remove_closure(db, day)
        crud.cancel_reservation(db, r["booking_code"])


def test_weekly_closing_day_comes_from_settings(monkeypatch):
    monday = future_date(open_day=False)
    with SessionLocal() as db:
        assert "chiuso" in book(db, "monday_test", date=monday)["error"]
        monkeypatch.setattr(settings, "CLOSED_WEEKDAYS", [])
        r = book(db, "monday_test", date=monday)
        assert r["success"] is True
        crud.cancel_reservation(db, r["booking_code"])


# ---------------------------------------------------------------- menu: dish type, sold out, sync, migration

def test_dish_type_filter_answers_the_meat_question():
    meat = {"Tagliere Campano", "Tagliata di Manzo al Rosmarino"}
    with SessionLocal() as db:
        assert {i["name"] for i in crud.get_menu_items(db, dish_type="carne")} == meat
        assert {i["name"] for i in crud.get_menu_items(db, dish_type="Carni")} == meat
        assert len(crud.get_menu_items(db, dish_type="pesce")) == 3
    assert "Orata" not in get_menu.invoke({"dish_type": "carne"})


def test_sold_out_dish_is_hidden_from_customers():
    with SessionLocal() as db:
        item = db.query(MenuItem).filter(MenuItem.name == "Tiramisù Artigianale").one()
        crud.update_menu_item(db, item.id, available=False)
        try:
            assert "Tiramisù Artigianale" not in {i["name"] for i in crud.get_menu_items(db, category="dolci")}
            assert "Tiramisù Artigianale" in {i["name"] for i in crud.get_menu_items(db, category="dolci", only_available=False)}
            assert "Tiramisù" not in get_menu.invoke({"category": "Dessert"})
        finally:
            crud.update_menu_item(db, item.id, available=True)


def test_sync_updates_an_existing_database_without_touching_sold_out_or_extra_dishes():
    with SessionLocal() as db:
        tag = db.query(MenuItem).filter(MenuItem.name == "Tagliata di Manzo al Rosmarino").one()
        tag.price, tag.available = 99.0, False                           # old price in the database, dish sold out
        db.query(RestaurantInfo).filter(RestaurantInfo.key == "opening_hours").update({"value": "vecchio orario"})
        db.add(MenuItem(category="Dessert", name="Piatto solo nel database", price=1.0, allergens=""))
        db.commit()
        crud.init_db()  # what happens at every start
        db.expire_all()
        tag = db.query(MenuItem).filter(MenuItem.name == "Tagliata di Manzo al Rosmarino").one()
        assert tag.price == 21.0               # corrected from the code
        assert tag.available is False          # staff decision kept
        assert crud.get_restaurant_info(db, "opening_hours")["opening_hours"] == opening_hours_text()
        extra = db.query(MenuItem).filter(MenuItem.name == "Piatto solo nel database").one()
        db.delete(extra)
        tag.available = True
        db.commit()


def test_old_database_files_get_the_new_columns(tmp_path):
    old = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with old.begin() as conn:
        conn.execute(text("CREATE TABLE menu_items (id INTEGER PRIMARY KEY, name TEXT)"))
        conn.execute(text("INSERT INTO menu_items (name) VALUES ('Vecchio piatto')"))
    crud._add_missing_columns(old)
    crud._add_missing_columns(old)  # twice: must be harmless
    with old.begin() as conn:
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(menu_items)")}
        assert {"dish_type", "available"} <= columns
        assert conn.execute(text("SELECT available FROM menu_items")).scalar() == 1  # existing rows are available


# ---------------------------------------------------------------- data retention

def test_purge_deletes_only_old_customers_without_recent_bookings():
    old_date = datetime.datetime.now() - datetime.timedelta(days=200)
    with SessionLocal() as db:
        gone, kept_recent_booking, kept_new = (crud.create_customer(db, n, "+393331234567")["customer_id"] for n in ("A", "B", "C"))
        db.query(Customer).filter(Customer.customer_id.in_([gone, kept_recent_booking])).update({"created_at": old_date})
        db.commit()
        r = book(db, kept_recent_booking)

        assert crud.purge_old_customers(db, days=90, dry_run=True) >= 1
        assert crud.is_registered_customer(db, gone)  # dry run changed nothing
        crud.purge_old_customers(db, days=90)
        assert not crud.is_registered_customer(db, gone)
        assert crud.is_registered_customer(db, kept_recent_booking)
        assert crud.is_registered_customer(db, kept_new)
        assert db.query(Reservation).filter(Reservation.booking_code == r["booking_code"]).count() == 1  # bookings stay
        crud.cancel_reservation(db, r["booking_code"])
