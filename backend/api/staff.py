"""Staff area for the restaurant owner: reservations with the customer's contact data, closures, sold-out dishes.

Everything here (except the HTML page, which contains no data) needs the header `X-API-Key` equal to
STAFF_API_KEY. If STAFF_API_KEY is empty the area is disabled. Customer names and phones are shown ONLY here:
they are never given to the LLM.
"""
import secrets
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from backend.api.schemas import ClosureRequest, MenuItemUpdate, StaffReservationUpdate
from backend.config import settings
from backend.database import crud
from backend.database.connection import get_db
from backend.database.models import Reservation

router = APIRouter(prefix="/staff", tags=["staff"])


def require_staff_key(x_api_key: Optional[str] = Header(None)):
    if not settings.STAFF_API_KEY:
        raise HTTPException(status_code=503, detail="Area staff disabilitata: imposta STAFF_API_KEY nel file .env.")
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.STAFF_API_KEY):
        raise HTTPException(status_code=401, detail="Chiave non valida.")


@router.get("", response_class=HTMLResponse, include_in_schema=False)
def staff_page():
    return STAFF_PAGE


@router.get("/reservations", dependencies=[Depends(require_staff_key)], summary="Prenotazioni con nome e telefono del cliente")
def staff_reservations(
    response: Response,
    date: Optional[str] = Query(None, description="AAAA-MM-GG. Se omessa: tutte da oggi in poi"),
    status: Optional[str] = Query(None, description="CONFIRMED o CANCELLED"),
    db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    response.headers["Cache-Control"] = "no-store"  # personal data: never kept by browsers or proxies
    return crud.list_reservations_for_staff(db, date=date, status=status)


def _owner_of(db: Session, booking_code: str) -> str:
    """customer_id that owns a booking. The staff acts on behalf of the owner: crud checks the owner, not the staff."""
    res = db.query(Reservation).filter(Reservation.booking_code == booking_code.strip().upper()).first()
    if res is None:
        raise HTTPException(status_code=404, detail=f"Prenotazione {booking_code} non trovata.")
    return res.customer_id


@router.patch("/reservations/{booking_code}", dependencies=[Depends(require_staff_key)], summary="Modifica una prenotazione (data, ora, persone, note)")
def staff_modify_reservation(booking_code: str, request: StaffReservationUpdate, db: Session = Depends(get_db)):
    result = crud.modify_reservation(
        db, booking_code,
        new_date=request.new_date, new_time=request.new_time,
        new_guests=request.new_guests, new_requests=request.new_requests,
        customer_id=_owner_of(db, booking_code),
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Errore nella modifica della prenotazione."))
    return result


@router.delete("/reservations/{booking_code}", dependencies=[Depends(require_staff_key)], summary="Cancella una prenotazione")
def staff_cancel_reservation(booking_code: str, db: Session = Depends(get_db)):
    result = crud.cancel_reservation(db, booking_code, customer_id=_owner_of(db, booking_code))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Errore nella cancellazione."))
    return result


@router.get("/menu", dependencies=[Depends(require_staff_key)], summary="Tutto il menu, compresi i piatti esauriti")
def staff_menu(db: Session = Depends(get_db)):
    return [
        {"id": m["id"], "category": m["category"], "name": m["name"], "price": m["price"], "available": m.get("available", True)}
        for m in crud.get_menu_items(db, only_available=False)
    ]


@router.get("/closures", dependencies=[Depends(require_staff_key)], summary="Giorni di chiusura straordinaria")
def staff_closures(db: Session = Depends(get_db)):
    return crud.list_closures(db)


@router.post("/closures", dependencies=[Depends(require_staff_key)], summary="Chiudi il ristorante in una data")
def staff_add_closure(request: ClosureRequest, db: Session = Depends(get_db)):
    result = crud.add_closure(db, request.date, request.reason)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.delete("/closures/{date}", dependencies=[Depends(require_staff_key)], summary="Riapri il ristorante in una data")
def staff_remove_closure(date: str, db: Session = Depends(get_db)):
    if not crud.remove_closure(db, date):
        raise HTTPException(status_code=404, detail=f"Nessuna chiusura il {date}.")
    return {"success": True, "date": date}


@router.patch("/menu/{item_id}", dependencies=[Depends(require_staff_key)], summary="Segna un piatto come esaurito o cambia il prezzo")
def staff_update_menu(item_id: int, request: MenuItemUpdate, db: Session = Depends(get_db)):
    updated = crud.update_menu_item(db, item_id, available=request.available, price=request.price)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Piatto {item_id} non trovato.")
    return updated


# A single self-contained page. Text coming from customers is inserted with textContent (never as HTML).
STAFF_PAGE = """<!doctype html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Prenotazioni - area staff</title>
<style>
 body{font-family:system-ui,sans-serif;margin:1.5rem;max-width:1000px}
 input,button,select{font:inherit;padding:.4rem .6rem;margin:.2rem}
 table{border-collapse:collapse;width:100%;margin-top:1rem}
 th,td{border-bottom:1px solid #ccc;padding:.4rem .5rem;text-align:left}
 .CANCELLED{color:#888;text-decoration:line-through}
 #msg{color:#b00}
</style></head><body>
<h1>Prenotazioni</h1>
<div>
 <input id="key" type="password" placeholder="Chiave staff">
 <input id="date" type="date">
 <select id="status"><option value="">tutte</option><option value="CONFIRMED">confermate</option><option value="CANCELLED">cancellate</option></select>
 <button id="go">Mostra</button>
</div>
<p id="msg"></p>
<table><thead><tr><th>Data</th><th>Ora</th><th>Persone</th><th>Tavolo</th><th>Cliente</th><th>Telefono</th><th>Note</th><th>Codice</th><th>Stato</th></tr></thead>
<tbody id="rows"></tbody></table>
<script>
const $ = id => document.getElementById(id);
$('key').value = sessionStorage.getItem('staffKey') || '';
async function load() {
  $('msg').textContent = '';
  sessionStorage.setItem('staffKey', $('key').value);
  const q = new URLSearchParams();
  if ($('date').value) q.set('date', $('date').value);
  if ($('status').value) q.set('status', $('status').value);
  const res = await fetch('/api/staff/reservations?' + q, {headers: {'X-API-Key': $('key').value}});
  if (!res.ok) { $('msg').textContent = (await res.json()).detail || 'Errore ' + res.status; $('rows').replaceChildren(); return; }
  const rows = await res.json();
  $('rows').replaceChildren(...rows.map(r => {
    const tr = document.createElement('tr'); tr.className = r.status;
    [r.date, r.time, r.guests_count, r.table_number ? r.table_number + ' (' + r.table_location + ')' : '',
     r.customer_name || '(anonimo)', r.customer_phone || '', r.special_requests || '', r.booking_code, r.status]
     .forEach(v => { const td = document.createElement('td'); td.textContent = v; tr.appendChild(td); });
    return tr;
  }));
  if (!rows.length) $('msg').textContent = 'Nessuna prenotazione.';
}
$('go').onclick = load;
</script></body></html>
"""
