"""Backend hardening: WAL/concorrenza/migrazioni (senior BE).

Verifica che check-then-insert sia atomico: N thread che prenotano l'unico tavolo
da 10 posti nello stesso slot -> esattamente 1 CONFIRMED, mai overbooking.
"""
import threading

from sqlalchemy import text

from backend.database.connection import SessionLocal, engine
from backend.database import crud
from backend.database.crud import (
    SCHEMA_VERSION,
    init_db,
    migrate_schema,
    create_reservation,
    cancel_reservation,
)


def test_sqlite_pragmas_wal_busy_timeout_fk():
    with engine.begin() as conn:
        assert conn.exec_driver_sql("PRAGMA journal_mode;").scalar().lower() == "wal"
        assert conn.exec_driver_sql("PRAGMA busy_timeout;").scalar() >= 5000
        assert conn.exec_driver_sql("PRAGMA foreign_keys;").scalar() == 1


def test_migrate_schema_idempotent():
    init_db()
    first = migrate_schema()
    assert first == SCHEMA_VERSION
    assert migrate_schema() == first  # re-run: no-op
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(menu_items)")}
        assert {"dish_type", "available"} <= cols
        assert conn.exec_driver_sql("SELECT version FROM schema_version").scalar() == SCHEMA_VERSION


def test_concurrent_bookings_single_big_table_no_overbooking():
    """8 thread sullo stesso slot da 10 coperti (un solo tavolo): 1 vince, 7 rifiutati."""
    init_db()
    date, time = "2026-11-17", "20:00"  # martedi', lontano dagli altri test
    barrier = threading.Barrier(8)
    results = []

    def book(i):
        with SessionLocal() as db:
            barrier.wait(timeout=10)
            results.append(create_reservation(
                db=db, date=date, time=time, guests=10,
                customer_id=f"load_user_{i}"))

    threads = [threading.Thread(target=book, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert len(results) == 8
    winners = [r for r in results if r.get("success")]
    assert len(winners) == 1, f"overbooking o deadlock: {results}"
    assert len({w["table_number"] for w in winners}) == 1

    # Lo slot e' pieno: una nona prenotazione da 10 deve fallire con messaggio pulito.
    with SessionLocal() as db:
        full = create_reservation(db=db, date=date, time=time, guests=10,
                                  customer_id="load_user_late")
        assert full["success"] is False
        cancel_reservation(db, winners[0]["booking_code"])


def test_failed_write_releases_lock():
    """Dopo un errore di validazione dentro la transazione, il DB resta utilizzabile."""
    init_db()
    with SessionLocal() as db:
        bad = create_reservation(db=db, date="2026-10-19", time="20:00",  # lunedi': chiuso
                                 guests=2, customer_id="lock_check_user")
        assert bad["success"] is False
        ok = create_reservation(db=db, date="2026-10-20", time="20:00",
                                guests=2, customer_id="lock_check_user")
        assert ok["success"] is True
        db.execute(text("SELECT 1")).scalar()  # nessun lock residuo
        cancel_reservation(db, ok["booking_code"])
