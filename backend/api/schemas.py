from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    message: str = Field(..., description="Messaggio dell'utente inviato dal bot chat o voice (pre-processato per rimuovere PII)")
    session_id: str = Field(..., description="ID univoco della sessione per mantenere il contesto conversazionale")
    customer_id: Optional[str] = Field(None, description="Identificativo anonimo del cliente (es. 'anon_user_123')")
    client_type: Optional[str] = Field("chat", description="Tipo di client chiamante: 'chat' oppure 'voice'")

class ChatResponse(BaseModel):
    reply: str = Field(..., description="Risposta conversazionale generata dall'assistente AI")
    session_id: str = Field(..., description="ID della sessione conversazionale")
    customer_id: str = Field(..., description="ID cliente anonimizzato")
    client_type: str = Field("chat", description="Tipo di client")
    timestamp: str = Field(..., description="Timestamp ISO della risposta")

class DirectReservationCreateRequest(BaseModel):
    date: str = Field(..., description="Data nel formato YYYY-MM-DD")
    time: str = Field(..., description="Orario nel formato HH:MM")
    guests: int = Field(..., ge=1, le=20, description="Numero di ospiti")
    customer_id: str = Field(default="anon_client", description="Token cliente anonimo")
    special_requests: Optional[str] = Field(None, description="Note o richieste speciali")
    preferred_location: Optional[str] = Field(None, description="interno, terrazza, giardino")

class DirectReservationModifyRequest(BaseModel):
    new_date: Optional[str] = Field(None, description="Nuova data (YYYY-MM-DD)")
    new_time: Optional[str] = Field(None, description="Nuovo orario (HH:MM)")
    new_guests: Optional[int] = Field(None, ge=1, le=20, description="Nuovo numero di ospiti")
    new_requests: Optional[str] = Field(None, description="Nuove note speciali")

class ReservationResponse(BaseModel):
    success: bool
    booking_code: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    shift: Optional[str] = None
    guests_count: Optional[int] = None
    table_number: Optional[int] = None
    table_location: Optional[str] = None
    status: Optional[str] = None
    special_requests: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None

class MenuItemResponse(BaseModel):
    id: int
    category: str
    name: str
    description: Optional[str] = None
    price: float
    allergens: str
    is_vegetarian: bool
    is_vegan: bool
    is_gluten_free: bool

class HealthResponse(BaseModel):
    status: str
    restaurant: str
    llm_provider: str
    llm_model: str
    database: str
