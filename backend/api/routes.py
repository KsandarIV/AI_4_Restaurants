import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database.connection import get_db
from backend.database import crud
from backend.graph.workflow import process_message
from backend.api.schemas import (
    ChatRequest,
    ChatResponse,
    DirectReservationCreateRequest,
    DirectReservationModifyRequest,
    ReservationResponse,
    MenuItemResponse,
    HealthResponse
)

router = APIRouter()

# -------------------------------------------------------------
# Conversational AI Endpoint for CHAT and VOICE Bots
# -------------------------------------------------------------
@router.post("/chat", response_model=ChatResponse, summary="Invia un messaggio all'assistente AI (per Chat e Voice)")
def chat_endpoint(request: ChatRequest):
    """
    Endpoint principale per la conversazione via LAN.
    Riceve il messaggio utente privo di PII (pre-processato dai client CHAT o VOICE)
    e restituisce la risposta elaborata tramite LangGraph e LangChain.
    """
    try:
        result = process_message(
            message=request.message,
            session_id=request.session_id,
            customer_id=request.customer_id,
            client_type=request.client_type or "chat"
        )
        return ChatResponse(
            reply=result["reply"],
            session_id=result["session_id"],
            customer_id=result["customer_id"],
            client_type=result["client_type"],
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Errore interno durante l'elaborazione conversazionale: {str(e)}"
        )

# -------------------------------------------------------------
# Direct CRUD Endpoints (Reservations, Menu, Info)
# -------------------------------------------------------------
@router.get("/reservations/{booking_code}", response_model=ReservationResponse, summary="Recupera stato prenotazione")
def get_reservation_endpoint(booking_code: str, db: Session = Depends(get_db)):
    res = crud.get_reservation(db, booking_code)
    if not res:
        raise HTTPException(status_code=404, detail=f"Prenotazione {booking_code} non trovata.")
    return ReservationResponse(success=True, **res)

@router.post("/reservations", response_model=ReservationResponse, summary="Crea prenotazione diretta")
def create_reservation_endpoint(request: DirectReservationCreateRequest, db: Session = Depends(get_db)):
    result = crud.create_reservation(
        db=db,
        date=request.date,
        time=request.time,
        guests=request.guests,
        customer_id=request.customer_id,
        special_requests=request.special_requests,
        preferred_location=request.preferred_location
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Errore nella creazione della prenotazione."))
    return ReservationResponse(**result)

@router.patch("/reservations/{booking_code}", response_model=ReservationResponse, summary="Modifica prenotazione")
def modify_reservation_endpoint(booking_code: str, request: DirectReservationModifyRequest, db: Session = Depends(get_db)):
    result = crud.modify_reservation(
        db=db,
        booking_code=booking_code,
        new_date=request.new_date,
        new_time=request.new_time,
        new_guests=request.new_guests,
        new_requests=request.new_requests
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Errore nella modifica della prenotazione."))
    return ReservationResponse(**result)

@router.delete("/reservations/{booking_code}", response_model=ReservationResponse, summary="Cancella prenotazione")
def cancel_reservation_endpoint(booking_code: str, db: Session = Depends(get_db)):
    result = crud.cancel_reservation(db=db, booking_code=booking_code)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Prenotazione non trovata."))
    return ReservationResponse(**result)

@router.get("/menu", response_model=List[MenuItemResponse], summary="Consulta menu con filtri")
def get_menu_endpoint(
    category: Optional[str] = Query(None, description="Filtra per categoria: Antipasti, Primi, Secondi, Contorni, Dessert, Bevande"),
    allergen_free: Optional[str] = Query(None, description="Escludi piatti contenenti un certo allergene (es. 'glutine')"),
    is_vegetarian: Optional[bool] = Query(None, description="Filtra solo piatti vegetariani"),
    is_vegan: Optional[bool] = Query(None, description="Filtra solo piatti vegani"),
    is_gluten_free: Optional[bool] = Query(None, description="Filtra solo piatti senza glutine"),
    db: Session = Depends(get_db)
):
    items = crud.get_menu_items(
        db=db,
        category=category,
        allergen_free=allergen_free,
        is_vegetarian=is_vegetarian,
        is_vegan=is_vegan,
        is_gluten_free=is_gluten_free
    )
    return items

@router.get("/info", summary="Informazioni generali sul ristorante")
def get_info_endpoint(key: Optional[str] = Query(None, description="Chiave specifica (es. address, opening_hours, phone, parking)"), db: Session = Depends(get_db)):
    return crud.get_restaurant_info(db, key=key)

@router.get("/health", response_model=HealthResponse, summary="Healthcheck e stato del server")
def health_endpoint():
    return HealthResponse(
        status="online",
        restaurant=settings.RESTAURANT_NAME,
        llm_provider=settings.LLM_PROVIDER,
        llm_model=settings.OLLAMA_MODEL,
        database="SQLite (connected)"
    )
