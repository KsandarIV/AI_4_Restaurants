from typing import Optional
from langchain_core.tools import tool
from backend.database.connection import SessionLocal
from backend.database import crud

@tool
def check_availability(date: str, time: str, guests: int, location: Optional[str] = None) -> str:
    """
    Verifica la disponibilità di tavoli per una data, orario e numero di ospiti.
    Parametri:
      - date: Data nel formato YYYY-MM-DD (es. '2026-10-20')
      - time: Orario nel formato HH:MM (es. '13:00' o '20:30')
      - guests: Numero di persone (intero da 1 a 20)
      - location: Preferenza sala ('interno', 'terrazza', 'giardino', facoltativo)
    """
    with SessionLocal() as db:
        date_ok, date_err, _ = crud.validate_date(date)
        if not date_ok:
            return date_err

        time_ok, time_err, shift = crud.validate_time_and_shift(time)
        if not time_ok:
            return time_err

        tables = crud.get_available_tables(
            db=db,
            date=date,
            time=time,
            guests=guests,
            preferred_location=location
        )
        if tables:
            return f"Disponibilità confermata! Abbiamo {len(tables)} tavoli adatti per {guests} persone per il giorno {date} alle {time} ({shift})."
        else:
            return f"Purtroppo non abbiamo tavoli disponibili per {guests} persone per il giorno {date} alle ore {time}."

@tool
def create_reservation(
    date: str,
    time: str,
    guests: int,
    customer_id: str = "anon_client",
    special_requests: Optional[str] = None,
    preferred_location: Optional[str] = None
) -> str:
    """
    Effettua la prenotazione di un tavolo nel ristorante e restituisce il codice univoco di prenotazione.
    Parametri:
      - date: Data in formato YYYY-MM-DD
      - time: Orario in formato HH:MM (es. '20:30')
      - guests: Numero di persone
      - customer_id: Token cliente anonimizzato (es. 'client_session_1')
      - special_requests: Richieste speciali (es. 'seggiolone per bimbo', 'intolleranze', 'tavolo appartato')
      - preferred_location: 'interno', 'terrazza' o 'giardino'
    """
    with SessionLocal() as db:
        res = crud.create_reservation(
            db=db,
            date=date,
            time=time,
            guests=guests,
            customer_id=customer_id,
            special_requests=special_requests,
            preferred_location=preferred_location
        )
        if res["success"]:
            loc_str = f" in {res['table_location']}" if res.get("table_location") else ""
            notes_str = f" Note: {res['special_requests']}." if res.get("special_requests") else ""
            return (
                f"Prenotazione confermata con successo! Codice di prenotazione: {res['booking_code']}. "
                f"Data: {res['date']}, Orario: {res['time']} ({res['shift']}), "
                f"Ospiti: {res['guests_count']} persone, Tavolo #{res['table_number']}{loc_str}.{notes_str} "
                f"Conservare il codice di prenotazione {res['booking_code']} per eventuali modifiche o cancellazioni."
            )
        else:
            return f"Impossibile effettuare la prenotazione: {res['error']}"

@tool
def get_reservation(booking_code: str, customer_id: Optional[str] = None) -> str:
    """
    Cerca e recupera i dettagli di una prenotazione esistente tramite il codice univoco (es. 'RES-A1B2C3').
    Il parametro customer_id è impostato automaticamente dal sistema: non chiederlo al cliente.
    """
    with SessionLocal() as db:
        res = crud.get_reservation(db, booking_code, customer_id=customer_id)
        if not res:
            return f"Nessuna prenotazione trovata con il codice {booking_code}. Verificare il codice inserito."

        status_str = "Attiva" if res["status"] == "CONFIRMED" else "Cancellata"
        notes_str = f", Note: {res['special_requests']}" if res.get("special_requests") else ""
        return (
            f"Dettagli prenotazione {res['booking_code']}: Stato: {status_str}, "
            f"Data: {res['date']}, Orario: {res['time']} ({res['shift']}), "
            f"Persone: {res['guests_count']}, Tavolo: #{res['table_number']} ({res['table_location']}){notes_str}."
        )

@tool
def modify_reservation(
    booking_code: str,
    new_date: Optional[str] = None,
    new_time: Optional[str] = None,
    new_guests: Optional[int] = None,
    new_requests: Optional[str] = None,
    customer_id: Optional[str] = None
) -> str:
    """
    Modifica una prenotazione esistente (data, orario, numero di ospiti o richieste speciali).
    Parametri:
      - booking_code: Il codice univoco della prenotazione da modificare (es. 'RES-ABC123')
      - new_date: Nuova data facoltativa (YYYY-MM-DD)
      - new_time: Nuovo orario facoltativo (HH:MM)
      - new_guests: Nuovo numero di persone facoltativo
      - new_requests: Nuove richieste o note speciali
      - customer_id: impostato automaticamente dal sistema, non chiederlo al cliente
    """
    with SessionLocal() as db:
        res = crud.modify_reservation(
            db=db,
            booking_code=booking_code,
            new_date=new_date,
            new_time=new_time,
            new_guests=new_guests,
            new_requests=new_requests,
            customer_id=customer_id
        )
        if res["success"]:
            return (
                f"Prenotazione {res['booking_code']} aggiornata con successo! "
                f"Nuovi dettagli: Data: {res['date']}, Orario: {res['time']}, "
                f"Ospiti: {res['guests_count']}, Tavolo #{res['table_number']}. "
                f"Note: {res.get('special_requests') or 'nessuna'}."
            )
        else:
            return f"Errore durante la modifica della prenotazione: {res['error']}"

@tool
def cancel_reservation(booking_code: str, customer_id: Optional[str] = None) -> str:
    """
    Cancella una prenotazione esistente tramite il codice di prenotazione (es. 'RES-XYZ789').
    Il parametro customer_id è impostato automaticamente dal sistema: non chiederlo al cliente.
    """
    with SessionLocal() as db:
        res = crud.cancel_reservation(db, booking_code, customer_id=customer_id)
        if res["success"]:
            return f"La prenotazione con codice {booking_code} è stata cancellata correttamente. Il tavolo è stato liberato."
        else:
            return f"Errore nella cancellazione: {res['error']}"

@tool
def get_menu(
    category: Optional[str] = None,
    allergen_free: Optional[str] = None,
    is_vegetarian: Optional[bool] = None,
    is_vegan: Optional[bool] = None,
    is_gluten_free: Optional[bool] = None
) -> str:
    """
    Consulta il menu del ristorante con opzioni di filtro per categoria (Antipasti, Primi, Secondi, Contorni, Dessert, Bevande)
    o esigenze dietetiche (senza glutine, vegetariano, vegano, o privo di uno specifico allergene).
    """
    with SessionLocal() as db:
        items = crud.get_menu_items(
            db=db,
            category=category,
            allergen_free=allergen_free,
            is_vegetarian=is_vegetarian,
            is_vegan=is_vegan,
            is_gluten_free=is_gluten_free
        )
        if not items:
            return "Nessun piatto trovato con i criteri di ricerca specificati."

        lines = []
        for item in items:
            flags = []
            if item["is_gluten_free"]:
                flags.append("Senza Glutine")
            if item["is_vegetarian"]:
                flags.append("Vegetariano")
            if item["is_vegan"]:
                flags.append("Vegano")
            flags_str = f" [{', '.join(flags)}]" if flags else ""
            allergens_str = f" (Allergeni: {item['allergens']})" if item['allergens'] else ""

            lines.append(
                f"- {item['name']} (€{item['price']:.2f}): {item['description']}{flags_str}{allergens_str}"
            )

        return "\n".join(lines)

@tool
def get_restaurant_info(key: Optional[str] = None) -> str:
    """
    Restituisce informazioni generali sulla Trattoria Bella Napoli.
    Parametro 'key' facoltativo: 'address' (indirizzo), 'opening_hours' (orari di apertura e turni),
    'phone' (telefono), 'email' (contatto), 'parking' (parcheggio), 'services' (servizi, animali, bimbi), 'payment_methods'.
    Se 'key' non è specificato, restituisce tutte le informazioni principali.
    """
    with SessionLocal() as db:
        info = crud.get_restaurant_info(db, key=key)
        if not info:
            return "Informazione non trovata."

        if key and key in info:
            return info[key]

        details = [
            f"Nome: {info.get('name', 'Trattoria Bella Napoli')}",
            f"Indirizzo: {info.get('address', '')}",
            f"Telefono: {info.get('phone', '')}",
            f"Email: {info.get('email', '')}",
            f"Orari: {info.get('opening_hours', '')}",
            f"Parcheggio: {info.get('parking', '')}",
            f"Servizi: {info.get('services', '')}",
            f"Pagamenti: {info.get('payment_methods', '')}"
        ]
        return "\n".join(details)

ALL_TOOLS = [
    check_availability,
    create_reservation,
    get_reservation,
    modify_reservation,
    cancel_reservation,
    get_menu,
    get_restaurant_info
]
