import logging
import random
import string
import datetime
import threading
import uuid
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from backend.database.connection import engine, Base, SessionLocal
from backend.database.models import RestaurantTable, Reservation, MenuItem, RestaurantInfo, Customer, Closure
from backend.database.seed_data import seed_database, sync_static_data, WEEKDAYS_IT
from backend.config import settings

logger = logging.getLogger("backend.db")

# Thread lock to prevent race conditions during concurrent table bookings
table_lock = threading.Lock()

# Versioned schema migrations for existing SQLite files (create_all only creates
# missing tables, it never alters them). Each step is idempotent: it checks PRAGMA
# first, so re-running init_db on an up-to-date file is a no-op.
# NOTE on Alembic: evaluated and deliberately deferred. Single-file SQLite, one writer
# process, two post-v1 column additions: an explicit registry below is fully auditable
# and covered by tests. If the schema grows beyond ~10 migrations, switch to Alembic
# (models are plain SQLAlchemy declarative, so `alembic init` + autogenerate works
# without touching crud.py).
_SCHEMA_MIGRATIONS = {
    2: [  # v1 -> v2: dish_type + available (sold-out flag managed by staff)
        ("menu_items", "dish_type", "VARCHAR(20)"),
        ("menu_items", "available", "BOOLEAN NOT NULL DEFAULT 1"),
    ],
}
SCHEMA_VERSION = max(_SCHEMA_MIGRATIONS, default=1)

# Backwards-compatible alias (same content as migration v2, single-step form).
_COLUMNS_ADDED_LATER = {
    "menu_items": {"dish_type": "VARCHAR(20)", "available": "BOOLEAN NOT NULL DEFAULT 1"},
}

def _add_missing_columns(eng=None):
    """Bring an existing SQLite file up to date (idempotent): adds the columns introduced after it was created."""
    eng = eng or engine
    if eng.dialect.name != "sqlite":
        return
    with eng.begin() as conn:
        for table, columns in _COLUMNS_ADDED_LATER.items():
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            for column, ddl in columns.items():
                if column not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

def _get_schema_version(eng=None) -> int:
    eng = eng or engine
    with eng.begin() as conn:
        tables = {row[0] for row in conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "schema_version" not in tables:
            return 1
        return conn.exec_driver_sql("SELECT version FROM schema_version").scalar() or 1

def migrate_schema(eng=None) -> int:
    """Apply pending versioned migrations, return the resulting schema version."""
    eng = eng or engine
    if eng.dialect.name != "sqlite":
        return SCHEMA_VERSION
    with eng.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
        current = conn.exec_driver_sql("SELECT version FROM schema_version").scalar() or 1
        for version in sorted(_SCHEMA_MIGRATIONS):
            if version <= current:
                continue
            for table, column, ddl in _SCHEMA_MIGRATIONS[version]:
                existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
                if column not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            conn.exec_driver_sql(
                "INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (version,))
            current = version
            logger.info("Migrazione schema applicata: v%s (tabella %s)", version, table)
    return current

def _begin_immediate(db: Session) -> None:
    """Take the SQLite RESERVED write lock BEFORE the availability check.

    The check-then-insert in create/modify must be one atomic unit: without this,
    two concurrent writers could both see the same table as free and overbook it.
    Must be called as the first statement inside `table_lock` (any read transaction
    opened by prior validation queries is closed first, validation is read-only).
    The matching COMMIT is the existing db.commit(); on error call db.rollback().
    No-op on non-SQLite backends.
    """
    if engine.dialect.name != "sqlite":
        return
    db.rollback()
    db.execute(text("BEGIN IMMEDIATE"))

def init_db():
    """Create all tables, update old database files, seed data and align menu/info with the code."""
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
    migrate_schema()
    with SessionLocal() as db:
        seed_database(db)
        sync_static_data(db)

# ------------------------------------------------------------------ customers

def create_customer(db: Session, name: str, phone: str) -> Dict[str, Any]:
    """Store a customer's contact data and return the anonymous customer_id clients must use from now on.

    The returned dict deliberately contains only the token: name and phone never leave the database.
    """
    customer = Customer(
        customer_id=f"cust_{uuid.uuid4().hex[:12]}",
        name=name.strip(),
        phone=phone.strip(),
        consent_at=datetime.datetime.now(datetime.timezone.utc)
    )
    db.add(customer)
    db.commit()
    return {"customer_id": customer.customer_id}

def is_registered_customer(db: Session, customer_id: Optional[str]) -> bool:
    """True if customer_id belongs to a customer registered through create_customer."""
    if not customer_id:
        return False
    return db.query(Customer.id).filter(Customer.customer_id == customer_id.strip()).first() is not None

def purge_old_customers(db: Session, days: int, dry_run: bool = False) -> int:
    """Delete name and phone of customers registered more than `days` ago with no booking since then.

    Their reservations stay (the customer_id token no longer points to anybody: they are anonymous).
    Returns how many customers were (or, with dry_run, would be) deleted.
    """
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)  # created_at is stored without timezone
    cutoff_date = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    recent = {row[0] for row in db.query(Reservation.customer_id).filter(Reservation.date >= cutoff_date)}
    old = db.query(Customer).filter(Customer.created_at < now - datetime.timedelta(days=days)).all()
    victims = [c for c in old if c.customer_id not in recent]
    if not dry_run:
        for c in victims:
            db.delete(c)
        db.commit()
    return len(victims)

def _can_access(reservation: Reservation, customer_id: Optional[str]) -> bool:
    """With registration enabled, only the customer who made a booking can read, modify or cancel it."""
    if not settings.REQUIRE_CUSTOMER_REGISTRATION:
        return True
    return bool(customer_id) and reservation.customer_id == customer_id.strip()

# ------------------------------------------------------------------ helpers

def generate_booking_code(db: Optional[Session] = None) -> str:
    """Generate a readable reservation code e.g. RES-9A8B2C, unique in the database when db is given."""
    for _ in range(20):
        code = "RES-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if db is None or db.query(Reservation.id).filter(Reservation.booking_code == code).first() is None:
            return code
    raise RuntimeError("Impossibile generare un codice di prenotazione univoco.")

def _clean_text(value: Optional[str], limit: int = 300) -> Optional[str]:
    """Free text typed by a customer: trimmed, empty -> None, capped in length."""
    if value is None:
        return None
    value = value.strip()
    return value[:limit] if value else None

def time_to_minutes(time_str: str) -> int:
    """Convert HH:MM string to minutes since midnight."""
    try:
        parts = time_str.strip().split(":")
        if len(parts) != 2:
            raise ValueError()
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError()
        return h * 60 + m
    except Exception:
        raise ValueError(f"Orario '{time_str}' non valido. Usare il formato HH:MM (es. 13:00, 20:30).")

def normalize_time(time_str: str) -> str:
    """'8:5' -> '08:05': the same time is always stored the same way."""
    minutes = time_to_minutes(time_str)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"

def validate_time_and_shift(time_str: str) -> Tuple[bool, str, str]:
    """
    Validate that the requested time falls within allowed booking windows.
    Returns: (is_valid, error_message, shift_name)
    """
    try:
        req_minutes = time_to_minutes(time_str)
    except ValueError as e:
        return False, str(e), "fuori_orario"

    lunch_start = time_to_minutes(settings.LUNCH_START)
    lunch_last = time_to_minutes(settings.LUNCH_LAST_BOOKING)
    dinner_start = time_to_minutes(settings.DINNER_START)
    dinner_last = time_to_minutes(settings.DINNER_LAST_BOOKING)

    if lunch_start <= req_minutes <= lunch_last:
        return True, "", "pranzo"
    elif dinner_start <= req_minutes <= dinner_last:
        return True, "", "cena"
    else:
        err = (
            f"Orario '{time_str}' non valido o fuori servizio. "
            f"Il pranzo è dalle {settings.LUNCH_START} alle {settings.LUNCH_END} (prenotazioni dalle {settings.LUNCH_START} alle {settings.LUNCH_LAST_BOOKING}), "
            f"la cena è dalle {settings.DINNER_START} alle {settings.DINNER_END} (prenotazioni dalle {settings.DINNER_START} alle {settings.DINNER_LAST_BOOKING})."
        )
        return False, err, "fuori_orario"

def determine_shift(time_str: str) -> str:
    """Helper to return 'pranzo', 'cena' or 'fuori_orario'."""
    is_valid, _, shift = validate_time_and_shift(time_str)
    return shift if is_valid else "fuori_orario"

def validate_date(date_str: str, db: Optional[Session] = None) -> Tuple[bool, str, Optional[datetime.date]]:
    """
    Validate date string (format YYYY-MM-DD, no past dates, no weekly closing day, no closure, max 120 days).
    Closures (holidays...) are checked only when a database session is given.
    """
    try:
        parts = date_str.strip().split("-")
        if len(parts) != 3 or len(parts[0]) != 4:
            return False, "Formato data non valido. Usare il formato AAAA-MM-GG (es. 2026-10-20).", None
        dt = datetime.datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except Exception:
        return False, "Data non valida o inesistente. Usare il formato AAAA-MM-GG (es. 2026-10-20).", None

    today = datetime.date.today()
    if dt < today:
        return False, f"Non è possibile prenotare per una data passata ({date_str}). Oggi è {today.isoformat()}.", None

    if dt.weekday() in settings.CLOSED_WEEKDAYS:
        return False, f"Il ristorante è chiuso il {WEEKDAYS_IT[dt.weekday()]} ({date_str}). Vi invitiamo a scegliere un altro giorno.", None

    if db is not None:
        closure = db.query(Closure).filter(Closure.date == dt.isoformat()).first()
        if closure:
            reason = f" ({closure.reason})" if closure.reason else ""
            return False, f"Il ristorante è chiuso il {dt.isoformat()}{reason}. Vi invitiamo a scegliere un altro giorno.", None

    max_future = today + datetime.timedelta(days=120)
    if dt > max_future:
        return False, f"È possibile prenotare al massimo con 120 giorni di anticipo (fino al {max_future.isoformat()}).", None

    return True, "", dt

def is_restaurant_open_on_date(date_str: str, db: Optional[Session] = None) -> bool:
    """Check if date is valid and restaurant is open."""
    is_valid, _, _ = validate_date(date_str, db)
    return is_valid

def get_available_tables(
    db: Session,
    date: str,
    time: str,
    guests: int,
    exclude_reservation_id: Optional[int] = None,
    preferred_location: Optional[str] = None
) -> List[RestaurantTable]:
    """
    Find available tables with capacity >= guests that are NOT occupied
    during the 90-minute window [time, time + 90 min] on the given date.
    Tables are ordered by capacity ascending (best fit first).
    """
    try:
        req_start = time_to_minutes(time)
    except Exception:
        return []

    req_end = req_start + settings.RESERVATION_DURATION_MINUTES

    # Base query for active tables with sufficient capacity
    query = db.query(RestaurantTable).filter(
        RestaurantTable.is_active == True,
        RestaurantTable.capacity >= guests
    )

    if preferred_location:
        loc = preferred_location.lower()
        if loc in ["terrazza", "giardino", "interno"]:
            query = query.filter(RestaurantTable.location == loc)

    candidate_tables = query.order_by(RestaurantTable.capacity.asc()).all()
    if not candidate_tables:
        return []

    # Fetch all confirmed reservations on that date
    res_query = db.query(Reservation).filter(
        Reservation.date == date,
        Reservation.status == "CONFIRMED"
    )
    if exclude_reservation_id:
        res_query = res_query.filter(Reservation.id != exclude_reservation_id)

    confirmed_reservations = res_query.all()

    # Determine which tables overlap with the requested [req_start, req_end] window
    busy_table_ids = set()
    for res in confirmed_reservations:
        try:
            res_start = time_to_minutes(res.time)
            res_end = res_start + settings.RESERVATION_DURATION_MINUTES
            # Overlap condition: max(start1, start2) < min(end1, end2)
            if max(req_start, res_start) < min(req_end, res_end):
                if res.table_id:
                    busy_table_ids.add(res.table_id)
        except Exception:
            continue

    # Filter out occupied tables
    available = [t for t in candidate_tables if t.id not in busy_table_ids]
    return available

def _restaurant_phone(db: Session) -> str:
    row = db.query(RestaurantInfo).filter(RestaurantInfo.key == "phone").first()
    return row.value if row else "il ristorante"

def validate_reservation_request(db: Session, date: str, time: str, guests: int, customer_id: str) -> Tuple[Optional[str], str]:
    """Checks every rule that does not depend on table availability.

    Shared by create_reservation and by the confirmation step of the conversation, so a booking
    that cannot be made is never proposed to the customer. Returns (error_message or None, shift).
    """
    date_ok, date_err, _ = validate_date(date, db)
    if not date_ok:
        return date_err, "fuori_orario"

    time_ok, time_err, shift = validate_time_and_shift(time)
    if not time_ok:
        return time_err, shift

    if guests <= 0:
        return f"Numero di ospiti ({guests}) non valido.", shift
    max_capacity = db.query(func.max(RestaurantTable.capacity)).filter(RestaurantTable.is_active == True).scalar() or 0
    if guests > max_capacity:
        return (
            f"Il nostro tavolo più grande ha {max_capacity} posti: per gruppi di più di {max_capacity} persone "
            f"vi preghiamo di contattarci telefonicamente al {_restaurant_phone(db)}.",
            shift
        )

    # The customer must have registered name and phone first (the LLM only ever sees the token)
    if settings.REQUIRE_CUSTOMER_REGISTRATION and not is_registered_customer(db, customer_id):
        return "Per prenotare serve prima la registrazione del nome e del numero di telefono.", shift

    return None, shift

# ------------------------------------------------------------------ reservations

def create_reservation(
    db: Session,
    date: str,
    time: str,
    guests: int,
    customer_id: str,
    special_requests: Optional[str] = None,
    preferred_location: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a new reservation in the database with concurrency lock and strict validations.
    """
    cid = (customer_id or "anon_client").strip()
    error, shift = validate_reservation_request(db, date, time, guests, cid)
    if error:
        return {"success": False, "error": error}
    time = normalize_time(time)

    # Thread-safe + crash-safe table allocation: in-process lock plus the SQLite
    # RESERVED write lock (BEGIN IMMEDIATE), so check-then-insert is atomic.
    with table_lock:
        _begin_immediate(db)
        try:
            available_tables = get_available_tables(
                db=db,
                date=date,
                time=time,
                guests=guests,
                preferred_location=preferred_location
            )

            # Fallback to any location if preferred location has no seats
            if not available_tables and preferred_location:
                available_tables = get_available_tables(
                    db=db,
                    date=date,
                    time=time,
                    guests=guests,
                    preferred_location=None
                )

            if not available_tables:
                db.rollback()
                return {
                    "success": False,
                    "error": (
                        f"Purtroppo non ci sono tavoli disponibili per {guests} persone in data {date} "
                        f"nella fascia oraria delle ore {time} (slot di {settings.RESERVATION_DURATION_MINUTES} min)."
                    )
                }

            chosen_table = available_tables[0]
            booking_code = generate_booking_code(db)

            reservation = Reservation(
                booking_code=booking_code,
                customer_id=cid,
                table_id=chosen_table.id,
                date=date.strip(),
                time=time,
                shift=shift,
                guests_count=guests,
                status="CONFIRMED",
                special_requests=_clean_text(special_requests)
            )

            db.add(reservation)
            db.commit()
            db.refresh(reservation)
        except Exception:
            db.rollback()
            logger.exception("create_reservation fallita (date=%s time=%s guests=%s)", date, time, guests)
            return {"success": False, "error": "Errore interno durante la prenotazione. Riprova tra poco."}

        logger.info(
            "Prenotazione %s creata: %s %s, %s coperti, tavolo #%s",
            reservation.booking_code, reservation.date, reservation.time,
            reservation.guests_count, chosen_table.table_number,
        )
        return {
            "success": True,
            "booking_code": reservation.booking_code,
            "customer_id": reservation.customer_id,
            "date": reservation.date,
            "time": reservation.time,
            "shift": reservation.shift,
            "guests_count": reservation.guests_count,
            "table_number": chosen_table.table_number,
            "table_location": chosen_table.location,
            "status": reservation.status,
            "special_requests": reservation.special_requests
        }

def get_reservation(db: Session, booking_code: str, customer_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve reservation details by booking code (None if not found or not owned by customer_id)."""
    res = db.query(Reservation).filter(
        Reservation.booking_code == booking_code.strip().upper()
    ).first()

    # Same answer for "does not exist" and "belongs to someone else": codes must not be guessable
    if not res or not _can_access(res, customer_id):
        return None

    table_num = res.table.table_number if res.table else None
    table_loc = res.table.location if res.table else None

    return {
        "id": res.id,
        "booking_code": res.booking_code,
        "customer_id": res.customer_id,
        "date": res.date,
        "time": res.time,
        "shift": res.shift,
        "guests_count": res.guests_count,
        "table_number": table_num,
        "table_location": table_loc,
        "status": res.status,
        "special_requests": res.special_requests,
        "created_at": res.created_at.isoformat() if res.created_at else None
    }

def modify_reservation(
    db: Session,
    booking_code: str,
    new_date: Optional[str] = None,
    new_time: Optional[str] = None,
    new_guests: Optional[int] = None,
    new_requests: Optional[str] = None,
    customer_id: Optional[str] = None
) -> Dict[str, Any]:
    """Modify an existing reservation with validations and thread-safe table re-check."""
    with table_lock:
        res = db.query(Reservation).filter(
            Reservation.booking_code == booking_code.strip().upper()
        ).first()

        if not res or not _can_access(res, customer_id):
            return {"success": False, "error": f"Prenotazione con codice {booking_code} non trovata."}

        if res.status == "CANCELLED":
            return {"success": False, "error": f"La prenotazione {booking_code} è già stata cancellata e non può essere modificata."}

        target_date = new_date.strip() if new_date else res.date
        target_time = new_time or res.time
        target_guests = new_guests or res.guests_count
        res_id = res.id

        # Read-only validations BEFORE taking the write lock (no transaction open yet).
        if new_date:
            date_ok, date_err, _ = validate_date(target_date, db)
            if not date_ok:
                return {"success": False, "error": date_err}

        if new_time:
            time_ok, time_err, _ = validate_time_and_shift(target_time)
            if not time_ok:
                return {"success": False, "error": time_err}
            target_time = normalize_time(target_time)

        date_or_time_changed = (new_date and target_date != res.date) or (new_time and target_time != res.time) or (new_guests and new_guests != res.guests_count)

        if date_or_time_changed:
            time_ok, time_err, shift = validate_time_and_shift(target_time)
            if not time_ok:
                return {"success": False, "error": time_err}
        else:
            # Notes-only change: single-row atomic update, no availability check needed.
            _begin_immediate(db)
            try:
                res = db.query(Reservation).filter(Reservation.id == res_id).first()
                if not res or not _can_access(res, customer_id):
                    db.rollback()
                    return {"success": False, "error": f"Prenotazione con codice {booking_code} non trovata."}
                if res.status == "CANCELLED":
                    db.rollback()
                    return {"success": False, "error": f"La prenotazione {booking_code} è già stata cancellata e non può essere modificata."}
                if new_requests is not None:
                    res.special_requests = _clean_text(new_requests)
                db.commit()
                db.refresh(res)
            except Exception:
                db.rollback()
                logger.exception("modify_reservation (note) fallita per %s", booking_code)
                return {"success": False, "error": "Errore interno durante la modifica. Riprova tra poco."}
            return {
                "success": True,
                "booking_code": res.booking_code,
                "customer_id": res.customer_id,
                "date": res.date,
                "time": res.time,
                "shift": res.shift,
                "guests_count": res.guests_count,
                "table_number": res.table.table_number if res.table else None,
                "status": res.status,
                "special_requests": res.special_requests
            }

        # Slot change: re-read the row INSIDE the write transaction, then
        # check-then-update atomically (prevents double booking of the new slot).
        _begin_immediate(db)
        try:
            res = db.query(Reservation).filter(Reservation.id == res_id).first()
            if not res or not _can_access(res, customer_id):
                db.rollback()
                return {"success": False, "error": f"Prenotazione con codice {booking_code} non trovata."}
            if res.status == "CANCELLED":
                db.rollback()
                return {"success": False, "error": f"La prenotazione {booking_code} è già stata cancellata e non può essere modificata."}

            candidates = get_available_tables(
                db=db,
                date=target_date,
                time=target_time,
                guests=target_guests,
                exclude_reservation_id=res.id
            )

            if not candidates:
                db.rollback()
                return {
                    "success": False,
                    "error": f"Nessun tavolo disponibile per {target_guests} persone in data {target_date} ore {target_time}."
                }

            # Keep the customer's table if it is still free and big enough; otherwise a table in the same room
            current_location = res.table.location if res.table else None
            chosen = (
                next((t for t in candidates if t.id == res.table_id), None)
                or next((t for t in candidates if current_location and t.location == current_location), None)
                or candidates[0]
            )

            res.table_id = chosen.id
            res.date = target_date
            res.time = target_time
            res.shift = shift
            res.guests_count = target_guests

            if new_requests is not None:
                res.special_requests = _clean_text(new_requests)

            db.commit()
            db.refresh(res)
        except Exception:
            db.rollback()
            logger.exception("modify_reservation fallita per %s", booking_code)
            return {"success": False, "error": "Errore interno durante la modifica. Riprova tra poco."}

        logger.info(
            "Prenotazione %s modificata: %s %s, %s coperti",
            res.booking_code, res.date, res.time, res.guests_count,
        )
        return {
            "success": True,
            "booking_code": res.booking_code,
            "customer_id": res.customer_id,
            "date": res.date,
            "time": res.time,
            "shift": res.shift,
            "guests_count": res.guests_count,
            "table_number": res.table.table_number if res.table else None,
            "status": res.status,
            "special_requests": res.special_requests
        }

def cancel_reservation(db: Session, booking_code: str, customer_id: Optional[str] = None) -> Dict[str, Any]:
    """Cancel an existing reservation."""
    with table_lock:
        res = db.query(Reservation).filter(
            Reservation.booking_code == booking_code.strip().upper()
        ).first()

        if not res or not _can_access(res, customer_id):
            return {"success": False, "error": f"Prenotazione con codice {booking_code} non trovata."}

        if res.status == "CANCELLED":
            return {"success": True, "message": f"La prenotazione {booking_code} era già stata cancellata.", "booking_code": booking_code}

        res_id = res.id
        _begin_immediate(db)
        try:
            res = db.query(Reservation).filter(Reservation.id == res_id).first()
            if not res or not _can_access(res, customer_id):
                db.rollback()
                return {"success": False, "error": f"Prenotazione con codice {booking_code} non trovata."}
            if res.status == "CANCELLED":
                db.commit()  # idempotent: nothing to change, release the write lock
                return {"success": True, "message": f"La prenotazione {booking_code} era già stata cancellata.", "booking_code": booking_code}
            res.status = "CANCELLED"
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("cancel_reservation fallita per %s", booking_code)
            return {"success": False, "error": "Errore interno durante la cancellazione. Riprova tra poco."}

        logger.info("Prenotazione %s cancellata.", res.booking_code)
        return {
            "success": True,
            "booking_code": res.booking_code,
            "customer_id": res.customer_id,
            "date": res.date,
            "time": res.time,
            "guests_count": res.guests_count,
            "status": "CANCELLED",
            "message": f"Prenotazione {res.booking_code} cancellata con successo."
        }

# ------------------------------------------------------------------ staff (restaurant owner)

def list_reservations_for_staff(db: Session, date: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Reservations with the customer's name and phone. ONLY for the staff area: never give this to the LLM."""
    query = db.query(Reservation)
    if date:
        query = query.filter(Reservation.date == date)
    else:
        query = query.filter(Reservation.date >= datetime.date.today().isoformat())
    if status:
        query = query.filter(Reservation.status == status.upper())
    result = []
    for r in query.order_by(Reservation.date, Reservation.time).all():
        customer = db.query(Customer).filter(Customer.customer_id == r.customer_id).first()
        result.append({
            "booking_code": r.booking_code,
            "date": r.date,
            "time": r.time,
            "guests_count": r.guests_count,
            "status": r.status,
            "table_number": r.table.table_number if r.table else None,
            "table_location": r.table.location if r.table else None,
            "special_requests": r.special_requests,
            "customer_name": customer.name if customer else None,
            "customer_phone": customer.phone if customer else None,
        })
    return result

def list_closures(db: Session) -> List[Dict[str, Any]]:
    return [{"date": c.date, "reason": c.reason} for c in db.query(Closure).order_by(Closure.date).all()]

def add_closure(db: Session, date: str, reason: Optional[str] = None) -> Dict[str, Any]:
    """Close the restaurant on a date. Existing confirmed reservations are NOT cancelled: the response lists them."""
    try:
        datetime.datetime.strptime(date.strip(), "%Y-%m-%d")
    except ValueError:
        return {"success": False, "error": "Data non valida. Usare il formato AAAA-MM-GG."}
    date = date.strip()
    if db.query(Closure).filter(Closure.date == date).first() is None:
        db.add(Closure(date=date, reason=_clean_text(reason, 200)))
        db.commit()
    affected = [r.booking_code for r in db.query(Reservation).filter(Reservation.date == date, Reservation.status == "CONFIRMED")]
    return {"success": True, "date": date, "reservations_to_handle": affected}

def remove_closure(db: Session, date: str) -> bool:
    closure = db.query(Closure).filter(Closure.date == date.strip()).first()
    if closure is None:
        return False
    db.delete(closure)
    db.commit()
    return True

def update_menu_item(db: Session, item_id: int, available: Optional[bool] = None, price: Optional[float] = None) -> Optional[Dict[str, Any]]:
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if item is None:
        return None
    if available is not None:
        item.available = available
    if price is not None:
        item.price = price
    db.commit()
    return {"id": item.id, "name": item.name, "available": item.available, "price": item.price}

# ------------------------------------------------------------------ menu and information

# Words a model (or a customer) may use for the menu categories
_MENU_CATEGORY_ALIASES = {
    "dolci": "Dessert", "dolce": "Dessert", "dessert": "Dessert", "dolci e dessert": "Dessert",
    "antipasto": "Antipasti", "primo": "Primi", "primi piatti": "Primi", "primo piatto": "Primi",
    "secondo": "Secondi", "secondi piatti": "Secondi", "secondo piatto": "Secondi", "contorno": "Contorni",
    "bevanda": "Bevande", "bevande": "Bevande", "vino": "Bevande", "vini": "Bevande", "acqua": "Bevande", "drink": "Bevande",
}

# Words used for the allergens in the menu ("lattosio", "glutine", "molluschi", "pesce", "uova", "solfiti")
_ALLERGEN_ALIASES = {
    "latticini": "lattosio", "latte": "lattosio", "formaggi": "lattosio", "formaggio": "lattosio", "derivati del latte": "lattosio",
    "frumento": "glutine", "grano": "glutine", "cereali": "glutine",
    "uovo": "uova", "frutti di mare": "molluschi", "vongole": "molluschi", "cozze": "molluschi",
    "solfito": "solfiti", "vino": "solfiti",
}

# Words used for the kind of dish
_DISH_TYPE_ALIASES = {"carni": "carne", "meat": "carne", "pesci": "pesce", "fish": "pesce", "verdura": "vegetale", "verdure": "vegetale",
                      "dolci": "dolce", "dessert": "dolce", "bevande": "bevanda", "bibite": "bevanda"}

class UnknownAllergen(ValueError):
    """The requested allergen is not one of those in the menu: answering 'none contains it' would be dangerous."""
    def __init__(self, allergen: str, known: List[str]):
        super().__init__(f"Allergene '{allergen}' non riconosciuto. Allergeni presenti nel menu: {', '.join(known)}.")
        self.allergen, self.known = allergen, known

def get_menu_items(
    db: Session,
    category: Optional[str] = None,
    allergen_free: Optional[str] = None,
    is_vegetarian: Optional[bool] = None,
    is_vegan: Optional[bool] = None,
    is_gluten_free: Optional[bool] = None,
    dish_type: Optional[str] = None,
    only_available: bool = True
) -> List[Dict[str, Any]]:
    """Retrieve menu items with optional dietary, category and dish-type filters (sold-out dishes hidden by default)."""
    query = db.query(MenuItem)

    if only_available:
        query = query.filter(MenuItem.available == True)

    if category:
        category = _MENU_CATEGORY_ALIASES.get(category.strip().lower(), category.strip())
        query = query.filter(MenuItem.category.ilike(f"%{category}%"))

    if dish_type:
        wanted = dish_type.strip().lower()
        query = query.filter(MenuItem.dish_type == _DISH_TYPE_ALIASES.get(wanted, wanted))

    if is_vegetarian is True:
        query = query.filter(MenuItem.is_vegetarian == True)

    if is_vegan is True:
        query = query.filter(MenuItem.is_vegan == True)

    if is_gluten_free is True:
        query = query.filter(MenuItem.is_gluten_free == True)

    items = query.all()

    if allergen_free:
        target = allergen_free.strip().lower()
        target = _ALLERGEN_ALIASES.get(target, target)
        known = sorted({a.strip().lower() for (allergens,) in db.query(MenuItem.allergens).all()
                        for a in (allergens or "").split(",") if a.strip()})
        if target not in known:
            raise UnknownAllergen(target, known)
        items = [i for i in items if target not in [a.strip().lower() for a in (i.allergens or "").split(",")]]

    return [
        {
            "id": i.id,
            "category": i.category,
            "name": i.name,
            "description": i.description,
            "price": i.price,
            "allergens": i.allergens,
            "is_vegetarian": i.is_vegetarian,
            "is_vegan": i.is_vegan,
            "is_gluten_free": i.is_gluten_free,
            "dish_type": i.dish_type,
            "available": i.available
        }
        for i in items
    ]

# Words used for the information keys ("opening_hours", "address", "phone", "parking", "services", ...)
_INFO_ALIASES = {
    "orari": "opening_hours", "orario": "opening_hours", "apertura": "opening_hours", "orari_di_apertura": "opening_hours",
    "opening": "opening_hours", "hours": "opening_hours", "turni": "opening_hours",
    "indirizzo": "address", "dove": "address", "posizione": "address", "location": "address",
    "telefono": "phone", "tel": "phone", "cellulare": "phone", "contatti": "phone", "numero": "phone",
    "mail": "email", "e-mail": "email", "parcheggio": "parking", "servizi": "services",
    "pagamenti": "payment_methods", "pagamento": "payment_methods", "payment": "payment_methods", "nome": "name",
}

def get_restaurant_info(db: Session, key: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve restaurant general information."""
    if key:
        normalized = key.strip().lower().replace(" ", "_")
        normalized = _INFO_ALIASES.get(normalized, normalized)
        item = db.query(RestaurantInfo).filter(RestaurantInfo.key == normalized).first()
        if item:
            return {item.key: item.value}
        return {}

    items = db.query(RestaurantInfo).all()
    return {item.key: item.value for item in items}
