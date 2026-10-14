import random
import string
import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from backend.database.connection import engine, Base, SessionLocal
from backend.database.models import RestaurantTable, Reservation, MenuItem, RestaurantInfo
from backend.database.seed_data import seed_database
from backend.config import settings

def init_db():
    """Create all tables and seed data."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)

def generate_booking_code() -> str:
    """Generate a readable, unique reservation code e.g. RES-9A8B2C."""
    chars = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"RES-{chars}"

def determine_shift(time_str: str) -> str:
    """Determine whether a time corresponds to 'pranzo' or 'cena'."""
    try:
        hour = int(time_str.split(":")[0])
        if 11 <= hour < 16:
            return "pranzo"
        elif 18 <= hour <= 23:
            return "cena"
        else:
            return "fuori_orario"
    except Exception:
        return "pranzo"

def is_restaurant_open_on_date(date_str: str) -> bool:
    """Check if restaurant is open (closed on Mondays)."""
    try:
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        # Monday is weekday 0
        if dt.weekday() == 0:
            return False
        return True
    except Exception:
        return True

def get_available_tables(
    db: Session,
    date: str,
    time: str,
    guests: int,
    exclude_reservation_id: Optional[int] = None,
    preferred_location: Optional[str] = None
) -> List[RestaurantTable]:
    """
    Find available tables with capacity >= guests on the given date and shift.
    Tables are ordered by capacity ascending (best fit first).
    """
    shift = determine_shift(time)

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

    # Find tables that are already booked for that date and shift
    booked_query = db.query(Reservation.table_id).filter(
        Reservation.date == date,
        Reservation.shift == shift,
        Reservation.status == "CONFIRMED"
    )

    if exclude_reservation_id:
        booked_query = booked_query.filter(Reservation.id != exclude_reservation_id)

    booked_table_ids = {r[0] for r in booked_query.all() if r[0] is not None}

    # Filter out occupied tables
    available_tables = [t for t in candidate_tables if t.id not in booked_table_ids]
    return available_tables

def create_reservation(
    db: Session,
    date: str,
    time: str,
    guests: int,
    customer_id: str,
    special_requests: Optional[str] = None,
    preferred_location: Optional[str] = None
) -> Dict[str, Any]:
    """Create a new reservation in the database."""
    # Check opening day
    if not is_restaurant_open_on_date(date):
        return {
            "success": False,
            "error": "Il ristorante è chiuso il Lunedì. Vi invitiamo a scegliere un altro giorno (Martedì - Domenica)."
        }

    # Validate time/shift
    shift = determine_shift(time)
    if shift == "fuori_orario":
        return {
            "success": False,
            "error": f"Orario {time} fuori dai turni del ristorante. Pranzo: {settings.LUNCH_START}-{settings.LUNCH_END}, Cena: {settings.DINNER_START}-{settings.DINNER_END}."
        }

    if guests <= 0 or guests > 20:
        return {
            "success": False,
            "error": f"Numero di ospiti ({guests}) non valido. Per gruppi superiori a 20 persone vi preghiamo di contattarci telefonicamente."
        }

    available_tables = get_available_tables(
        db=db,
        date=date,
        time=time,
        guests=guests,
        preferred_location=preferred_location
    )

    # If preferred location had no tables, try without location preference
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
            "error": f"Purtroppo non ci sono tavoli disponibili per {guests} persone in data {date} ore {time} ({shift})."
        }

    chosen_table = available_tables[0]
    booking_code = generate_booking_code()

    reservation = Reservation(
        booking_code=booking_code,
        customer_id=customer_id,
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
        "date": reservation.date,
        "time": reservation.time,
        "shift": reservation.shift,
        "guests_count": reservation.guests_count,
        "table_number": chosen_table.table_number,
        "table_location": chosen_table.location,
        "status": reservation.status,
        "special_requests": reservation.special_requests
    }

def get_reservation(db: Session, booking_code: str) -> Optional[Dict[str, Any]]:
    """Retrieve reservation details by booking code."""
    res = db.query(Reservation).filter(
        Reservation.booking_code == booking_code.strip().upper()
    ).first()

    if not res:
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
    new_requests: Optional[str] = None
) -> Dict[str, Any]:
    """Modify an existing reservation."""
    res = db.query(Reservation).filter(
        Reservation.booking_code == booking_code.strip().upper()
    ).first()

    if not res:
        return {"success": False, "error": f"Prenotazione con codice {booking_code} non trovata."}

    if res.status == "CANCELLED":
        return {"success": False, "error": f"La prenotazione {booking_code} è già stata cancellata e non può essere modificata."}

    target_date = new_date or res.date
    target_time = new_time or res.time
    target_guests = new_guests or res.guests_count

    # If date is changing, check opening day
    if new_date and not is_restaurant_open_on_date(target_date):
        return {
            "success": False,
            "error": "Il ristorante è chiuso il Lunedì. Scegliere una data dal Martedì alla Domenica."
        }

    # If date, time, or guests change, check availability
    date_or_time_changed = (new_date and new_date != res.date) or (new_time and new_time != res.time) or (new_guests and new_guests != res.guests_count)

    if date_or_time_changed:
        shift = determine_shift(target_time)
        if shift == "fuori_orario":
            return {"success": False, "error": f"Orario {target_time} fuori dai turni del ristorante."}

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
        "date": res.date,
        "time": res.time,
        "shift": res.shift,
        "guests_count": res.guests_count,
        "table_number": res.table.table_number if res.table else None,
        "status": res.status,
        "special_requests": res.special_requests
    }

def cancel_reservation(db: Session, booking_code: str) -> Dict[str, Any]:
    """Cancel an existing reservation."""
    res = db.query(Reservation).filter(
        Reservation.booking_code == booking_code.strip().upper()
    ).first()

    if not res:
        return {"success": False, "error": f"Prenotazione con codice {booking_code} non trovata."}

    if res.status == "CANCELLED":
        return {"success": True, "message": f"La prenotazione {booking_code} era già stata cancellata.", "booking_code": booking_code}

    res.status = "CANCELLED"
    db.commit()

    return {
        "success": True,
        "booking_code": res.booking_code,
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
        # Match case-insensitively
        query = query.filter(MenuItem.category.ilike(f"%{category.strip()}%"))

    if is_vegetarian is True:
        query = query.filter(MenuItem.is_vegetarian == True)

    if is_vegan is True:
        query = query.filter(MenuItem.is_vegan == True)

    if is_gluten_free is True:
        query = query.filter(MenuItem.is_gluten_free == True)

    items = query.all()

    # Filter out items containing specific allergens if requested
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
