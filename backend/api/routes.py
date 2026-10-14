import json
import datetime
import asyncio
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database.connection import get_db
from backend.database import crud
from backend.graph.workflow import process_message
from backend.api.schemas import (
    ChatRequest,
    ChatResponse,
    CustomerCreateRequest,
    CustomerResponse,
    DirectReservationCreateRequest,
    DirectReservationModifyRequest,
    ReservationResponse,
    MenuItemResponse,
    HealthResponse
)

router = APIRouter()

# -------------------------------------------------------------
# Customer registration (called by CHAT and VOICE BEFORE the conversation)
# -------------------------------------------------------------
@router.post("/customers", response_model=CustomerResponse, summary="Registra il cliente (nome e telefono) e restituisce un customer_id anonimo")
def create_customer_endpoint(request: CustomerCreateRequest, db: Session = Depends(get_db)):
    """
    Nome e telefono vengono salvati solo nella tabella `customers`. Il client usa poi il
    `customer_id` restituito in /api/chat: l'LLM non vede mai i dati personali.
    """
    return CustomerResponse(**crud.create_customer(db, name=request.name, phone=request.phone))

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

@router.post("/chat/stream", summary="SSE Streaming endpoint per VoiceBot e ChatBot")
async def chat_stream_endpoint(request: Request):
    """
    SSE stream endpoint compatible with VoiceBot client contract:
    Receives JSON with 'messages' or 'message', streams tokens:
      data: {"token": "..."}
      ...
      data: [DONE]
    """
    body = await request.json()
    message_text = ""
    session_id = body.get("session_id", "voice_stream_sess")
    customer_id = body.get("customer_id") or "anon_voice"  # never body["name"]: a name is personal data
    client_type = body.get("client_type", "voice")

    if "messages" in body and isinstance(body["messages"], list):
        # Extract the last user message
        for m in reversed(body["messages"]):
            if m.get("role") == "user":
                message_text = m.get("content", "")
                break
    elif "message" in body:
        message_text = str(body["message"])

    if not message_text:
        message_text = "Buongiorno"

    # Process message with LangGraph
    result = process_message(
        message=message_text,
        session_id=session_id,
        customer_id=customer_id,
        client_type=client_type
    )
    reply_text = result["reply"]

    async def event_generator():
        # Stream response word by word for natural voice TTS consumption
        words = reply_text.split(" ")
        for i, word in enumerate(words):
            token = word + (" " if i < len(words) - 1 else "")
            payload = json.dumps({"token": token})
            yield f"data: {payload}\n\n"
            await asyncio.sleep(0.03)
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# -------------------------------------------------------------
# Direct CRUD Endpoints (Reservations, Menu, Availability, Info)
# -------------------------------------------------------------
@router.get("/availability", summary="Verifica disponibilità tavoli (utilizzato dal VoiceBot)")
def get_availability_endpoint(
    date: str = Query(..., description="Data YYYY-MM-DD"),
    time: str = Query(..., description="Orario HH:MM"),
    party_size: Optional[int] = Query(None, description="Numero persone (alias)"),
    guests: Optional[int] = Query(None, description="Numero persone"),
    db: Session = Depends(get_db)
):
    num_guests = party_size or guests or 2
    tables = crud.get_available_tables(db=db, date=date, time=time, guests=num_guests)
    return {
        "available": len(tables) > 0,
        "tables_count": len(tables),
        "date": date,
        "time": time,
        "party_size": num_guests
    }

@router.get("/reservations/{booking_code}", response_model=ReservationResponse, summary="Recupera stato prenotazione")
def get_reservation_endpoint(
    booking_code: str,
    customer_id: Optional[str] = Query(None, description="Cliente che ha fatto la prenotazione (obbligatorio se la registrazione è attiva)"),
    db: Session = Depends(get_db)
):
    res = crud.get_reservation(db, booking_code, customer_id=customer_id)
    if not res:
        raise HTTPException(status_code=404, detail=f"Prenotazione {booking_code} non trovata.")
    return ReservationResponse(success=True, **res)

@router.post("/reservations", response_model=ReservationResponse, summary="Crea prenotazione diretta")
def create_reservation_endpoint(request: DirectReservationCreateRequest, db: Session = Depends(get_db)):
    num_guests = request.guests or request.party_size
    if not num_guests:
        raise HTTPException(status_code=400, detail="Specificare il numero di persone ('guests' o 'party_size').")

    cid = request.customer_id or "anon_client"  # request.name is ignored on purpose (personal data)

    result = crud.create_reservation(
        db=db,
        date=request.date,
        time=request.time,
        guests=num_guests,
        customer_id=cid,
        special_requests=request.special_requests,
        preferred_location=request.preferred_location
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Errore nella creazione della prenotazione."))
    return ReservationResponse(**result)

@router.patch("/reservations/{booking_code}", response_model=ReservationResponse, summary="Modifica prenotazione")
@router.put("/reservations/{booking_code}", response_model=ReservationResponse, summary="Modifica prenotazione (alias PUT)")
def modify_reservation_endpoint(booking_code: str, request: DirectReservationModifyRequest, db: Session = Depends(get_db)):
    new_g = request.new_guests or request.party_size
    result = crud.modify_reservation(
        db=db,
        booking_code=booking_code,
        new_date=request.new_date,
        new_time=request.new_time,
        new_guests=new_g,
        new_requests=request.new_requests,
        customer_id=request.customer_id
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Errore nella modifica della prenotazione."))
    return ReservationResponse(**result)

@router.delete("/reservations/{booking_code}", response_model=ReservationResponse, summary="Cancella prenotazione")
def cancel_reservation_endpoint(
    booking_code: str,
    customer_id: Optional[str] = Query(None, description="Cliente che ha fatto la prenotazione (obbligatorio se la registrazione è attiva)"),
    db: Session = Depends(get_db)
):
    result = crud.cancel_reservation(db=db, booking_code=booking_code, customer_id=customer_id)
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
