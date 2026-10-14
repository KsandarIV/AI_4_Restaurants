import random
import string
import datetime
import threading
import uuid
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from backend.database.connection import engine, Base, SessionLocal
from backend.database.models import RestaurantTable, Reservation, MenuItem, RestaurantInfo, Customer
from backend.database.seed_data import seed_database
from backend.config import settings

# Thread lock to prevent race conditions during concurrent table bookings
table_lock = threading.Lock()

def init_db():
    """Create all tables and seed data."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)

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

def _can_access(reservation: Reservation, customer_id: Optional[str]) -> bool:
    """With registration enabled, only the customer who made a booking can read, modify or cancel it."""
    if not settings.REQUIRE_CUSTOMER_REGISTRATION:
        return True
    return bool(customer_id) and reservation.customer_id == customer_id.strip()

def generate_booking_code() -> str:
    """Generate a readable, unique reservation code e.g. RES-9A8B2C."""
    chars = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"RES-{chars}"

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

def validate_date(date_str: str) -> Tuple[bool, str, Optional[datetime.date]]:
    """
    Validate date string (format YYYY-MM-DD, no past dates, no Mondays, max 120 days).
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

    # Monday check (weekday 0 is Monday)
    if dt.weekday() == 0:
        return False, f"Il ristorante è chiuso il Lunedì ({date_str}). Vi invitiamo a scegliere un giorno dal Martedì alla Domenica.", None

    max_future = today + datetime.timedelta(days=120)
    if dt > max_future:
        return False, f"È possibile prenotare al massimo con 120 giorni di anticipo (fino al {max_future.isoformat()}).", None

    return True, "", dt

def is_restaurant_open_on_date(date_str: str) -> bool:
    """Check if date is valid and restaurant is open."""
    is_valid, _, _ = validate_date(date_str)
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
    # 1. Validate date
    date_ok, date_err, _ = validate_date(date)
    if not date_ok:
        return {"success": False, "error": date_err}

    # 2. Validate time and shift
    time_ok, time_err, shift = validate_time_and_shift(time)
    if not time_ok:
        return {"success": False, "error": time_err}

    # 3. Validate party size
    if guests <= 0 or guests > 20:
        return {
            "success": False,
            "error": f"Numero di ospiti ({guests}) non valido. Per gruppi superiori a 20 persone vi preghiamo di contattarci telefonicamente."
        }

    # Clean customer_id
    cid = (customer_id or "anon_client").strip()

    # 4. The customer must have registered name and phone first (the LLM only ever sees the token)
    if settings.REQUIRE_CUSTOMER_REGISTRATION and not is_registered_customer(db, cid):
        return {
            "success": False,
            "error": "Per prenotare serve prima la registrazione del nome e del numero di telefono."
        }

    # Thread-safe table allocation
    with table_lock:
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
            return {
                "success": False,
                "error": (
                    f"Purtroppo non ci sono tavoli disponibili per {guests} persone in data {date} "
                    f"nella fascia oraria delle ore {time} (slot di {settings.RESERVATION_DURATION_MINUTES} min)."
                )
            }

        chosen_table = available_tables[0]
        booking_code = generate_booking_code()

        reservation = Reservation(
            booking_code=booking_code,
            customer_id=cid,
            table_id=chosen_table.id,
            date=date,
            time=time,
            shift=shift,
            guests_count=guests,
            status="CONFIRMED",
            special_requests=special_requests
        )

        db.add(reservation)
        db.commit()
        db.refresh(reservation)

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

        target_date = new_date or res.date
        target_time = new_time or res.time
        target_guests = new_guests or res.guests_count

        # Validate date if changed
        if new_date:
            date_ok, date_err, _ = validate_date(target_date)
            if not date_ok:
                return {"success": False, "error": date_err}

        # Validate time if changed
        if new_time:
            time_ok, time_err, _ = validate_time_and_shift(target_time)
            if not time_ok:
                return {"success": False, "error": time_err}

        date_or_time_changed = (new_date and new_date != res.date) or (new_time and new_time != res.time) or (new_guests and new_guests != res.guests_count)

        if date_or_time_changed:
            time_ok, time_err, shift = validate_time_and_shift(target_time)
            if not time_ok:
                return {"success": False, "error": time_err}

            available_tables = get_available_tables(
                db=db,
                date=target_date,
                time=target_time,
                guests=target_guests,
                exclude_reservation_id=res.id
            )

            if not available_tables:
                return {
                    "success": False,
                    "error": f"Nessun tavolo disponibile per {target_guests} persone in data {target_date} ore {target_time}."
                }

            res.table_id = available_tables[0].id
            res.date = target_date
            res.time = target_time
            res.shift = shift
            res.guests_count = target_guests

        if new_requests is not None:
            res.special_requests = new_requests

        db.commit()
        db.refresh(res)

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

        res.status = "CANCELLED"
        db.commit()

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

def get_menu_items(
    db: Session,
    category: Optional[str] = None,
    allergen_free: Optional[str] = None,
    is_vegetarian: Optional[bool] = None,
    is_vegan: Optional[bool] = None,
    is_gluten_free: Optional[bool] = None
) -> List[Dict[str, Any]]:
    """Retrieve menu items with optional dietary and category filters."""
    query = db.query(MenuItem)

    if category:
        query = query.filter(MenuItem.category.ilike(f"%{category.strip()}%"))

    if is_vegetarian is True:
        query = query.filter(MenuItem.is_vegetarian == True)

    if is_vegan is True:
        query = query.filter(MenuItem.is_vegan == True)

    if is_gluten_free is True:
        query = query.filter(MenuItem.is_gluten_free == True)

    items = query.all()

    if allergen_free:
        allergen_target = allergen_free.strip().lower()
        items = [i for i in items if allergen_target not in i.allergens.lower()]

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
            "is_gluten_free": i.is_gluten_free
        }
        for i in items
    ]

def get_restaurant_info(db: Session, key: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve restaurant general information."""
    if key:
        item = db.query(RestaurantInfo).filter(RestaurantInfo.key == key.strip().lower()).first()
        if item:
            return {item.key: item.value}
        return {}

    items = db.query(RestaurantInfo).all()
    return {item.key: item.value for item in items}
