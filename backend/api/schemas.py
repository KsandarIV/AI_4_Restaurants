from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator

class CustomerCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, description="Nome (e cognome) del cliente")
    phone: str = Field(..., pattern=r"^\+[1-9]\d{7,14}$", description="Telefono in formato internazionale E.164, es. +393331234567")
    consent: bool = Field(..., description="Il cliente ha accettato l'uso dei dati per gestire la prenotazione (deve essere true)")

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Il nome non può essere vuoto.")
        return v

    @field_validator("consent")
    @classmethod
    def consent_given(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("Serve il consenso al trattamento dei dati.")
        return v

class CustomerResponse(BaseModel):
    customer_id: str = Field(..., description="Identificativo anonimo da usare in tutte le chiamate successive")

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
    guests: Optional[int] = Field(None, ge=1, le=20, description="Numero di ospiti")
    party_size: Optional[int] = Field(None, ge=1, le=20, description="Alias per guests")
    customer_id: Optional[str] = Field(default="anon_client", description="Token cliente anonimo")
    name: Optional[str] = Field(None, description="DEPRECATO e ignorato: un nome non è mai usato come customer_id (dato personale). Registrare il cliente con POST /api/customers.")
    special_requests: Optional[str] = Field(None, description="Note o richieste speciali")
    preferred_location: Optional[str] = Field(None, description="interno, terrazza, giardino")

class DirectReservationModifyRequest(BaseModel):
    new_date: Optional[str] = Field(None, description="Nuova data (YYYY-MM-DD)")
    new_time: Optional[str] = Field(None, description="Nuovo orario (HH:MM)")
    new_guests: Optional[int] = Field(None, ge=1, le=20, description="Nuovo numero di ospiti")
    party_size: Optional[int] = Field(None, ge=1, le=20, description="Alias per new_guests")
    new_requests: Optional[str] = Field(None, description="Nuove note speciali")
    customer_id: Optional[str] = Field(None, description="Cliente che ha fatto la prenotazione (obbligatorio se la registrazione è attiva)")

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
    dish_type: Optional[str] = None
    available: bool = True

class HealthResponse(BaseModel):
    status: str = Field(..., description="'online' se database e modello rispondono, altrimenti 'degraded'")
    restaurant: str
    llm_provider: str
    llm_model: str
    database: str
    llm_reachable: Optional[bool] = Field(None, description="Il server del modello (Ollama) risponde")
    llm_model_available: Optional[bool] = Field(None, description="Il modello configurato è installato")

class ClosureRequest(BaseModel):
    date: str = Field(..., description="Data di chiusura AAAA-MM-GG")
    reason: Optional[str] = Field(None, max_length=200, description="Motivo (es. Ferragosto)")

class StaffReservationUpdate(BaseModel):
    new_date: Optional[str] = Field(None, description="Nuova data (AAAA-MM-GG)")
    new_time: Optional[str] = Field(None, description="Nuovo orario (HH:MM)")
    new_guests: Optional[int] = Field(None, ge=1, le=20, description="Nuovo numero di ospiti")
    new_requests: Optional[str] = Field(None, description="Nuove note speciali (stringa vuota = nessuna nota)")

class MenuItemUpdate(BaseModel):
    available: Optional[bool] = Field(None, description="false = piatto esaurito, non viene più proposto")
    price: Optional[float] = Field(None, gt=0)
