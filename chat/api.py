"""Servizio HTTP del componente CHAT, usato dal sito web (cartella frontend/).

Avvio (dalla cartella chat/):  python -m uvicorn api:app --host 0.0.0.0 --port 8002

Fa le stesse cose di app.py (la versione Streamlit), ma esposto come API:
  POST /chat/session   -> crea una conversazione, risponde col messaggio iniziale
  POST /chat/message   -> un messaggio dell'utente; risponde col testo del bot
Il browser non parla mai direttamente col BE per la chat: i dati personali passano
da qui, dove vengono anonimizzati (anonimizzatore.py) o inviati solo a /api/customers
(contatti.py). L'LLM del BE vede solo testo anonimo e un customer_id.
"""
import os
import time
import uuid

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from anonimizzatore import Anonimizzatore
from contatti import MESSAGGIO_INIZIALE, Registrazione

BE_URL = os.getenv("BE_URL", "http://localhost:8000").rstrip("/")
TIMEOUT_SECONDI = 120  # l'LLM locale può essere lento
MAX_SESSIONI = 500
MESSAGGIO_BENVENUTO = (
    "Registrazione completata. Come posso aiutarla? Posso prenotare, modificare o cancellare un tavolo, "
    "mostrarle il menu o darle informazioni sul locale."
)

app = FastAPI(title="CHAT - Trattoria Bella Napoli")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

sessioni = {}  # session_id -> Sessione (in memoria: si perde al riavvio del servizio)


class Sessione:
    def __init__(self):
        self.session_id = f"chat_{uuid.uuid4().hex[:8]}"
        self.customer_id = f"anon_{uuid.uuid4().hex[:6]}"  # sostituito da quello del BE a registrazione fatta
        self.anonimizzatore = Anonimizzatore()
        self.registrazione = Registrazione()
        self.fase = "registrazione"  # poi "chat"
        self.ultimo_uso = time.time()


class MessaggioIn(BaseModel):
    session_id: str
    text: str = Field(..., min_length=1, max_length=2000)


def _errore_di_rete(errore):
    if isinstance(errore, requests.Timeout):
        return RuntimeError("Il server ci sta mettendo troppo a rispondere. Riprova tra poco.")
    return RuntimeError("Non riesco a raggiungere il server. Controlla che il BE sia acceso e l'indirizzo sia corretto.")


def registra_cliente(nome, telefono):
    """Invia nome e telefono al BE e restituisce il customer_id anonimo che il BE assegna."""
    payload = {"name": nome, "phone": telefono, "consent": True}
    try:
        risposta = requests.post(f"{BE_URL}/api/customers", json=payload, timeout=30)
    except (requests.ConnectionError, requests.Timeout) as errore:
        raise _errore_di_rete(errore)
    if risposta.status_code in (404, 405):
        raise RuntimeError("Il server non supporta ancora la registrazione dei clienti.")
    if not risposta.ok:
        raise RuntimeError(f"Il server ha rifiutato la registrazione ({risposta.status_code}).")
    try:
        return risposta.json()["customer_id"]
    except (ValueError, KeyError):
        raise RuntimeError("Risposta del server in un formato inatteso.")


def chiedi_al_be(sessione, testo_anonimo):
    """Invia il messaggio (già anonimo) al BE e restituisce il testo della risposta."""
    payload = {
        "message": testo_anonimo,
        "session_id": sessione.session_id,
        "customer_id": sessione.customer_id,
        "client_type": "chat",
    }
    try:
        risposta = requests.post(f"{BE_URL}/api/chat", json=payload, timeout=TIMEOUT_SECONDI)
    except (requests.ConnectionError, requests.Timeout) as errore:
        raise _errore_di_rete(errore)
    if risposta.status_code != 200:
        raise RuntimeError(f"Il server ha risposto con un errore ({risposta.status_code}).")
    try:
        return risposta.json()["reply"]
    except (ValueError, KeyError):
        raise RuntimeError("Risposta del server in un formato inatteso.")


def gestisci_registrazione(sessione, testo):
    """Un passo del dialogo di registrazione. Restituisce la risposta del bot."""
    registrazione = sessione.registrazione
    risposta, azione = registrazione.gestisci(testo)
    if azione == "registra":
        try:
            sessione.customer_id = registra_cliente(registrazione.nome, registrazione.telefono)
            sessione.fase = "chat"
            risposta = f"Grazie {registrazione.nome}! {MESSAGGIO_BENVENUTO}"
        except RuntimeError as errore:
            registrazione.fase = "conferma"  # i dati restano: basta riscrivere "sì" per riprovare
            risposta = f"{errore} Quando vuole, scriva sì per riprovare."
    elif azione == "rinuncia":
        sessione.fase = "chat"  # prosegue con il customer_id anonimo
    return risposta


def _pulisci_sessioni():
    if len(sessioni) >= MAX_SESSIONI:
        for sid in sorted(sessioni, key=lambda s: sessioni[s].ultimo_uso)[: MAX_SESSIONI // 5]:
            del sessioni[sid]


@app.get("/health")
def health():
    return {"status": "ok", "be_url": BE_URL}


@app.post("/chat/session")
def nuova_sessione():
    _pulisci_sessioni()
    sessione = Sessione()
    sessioni[sessione.session_id] = sessione
    return {"session_id": sessione.session_id, "phase": sessione.fase, "reply": MESSAGGIO_INIZIALE}


@app.post("/chat/message")
def messaggio(richiesta: MessaggioIn):
    sessione = sessioni.get(richiesta.session_id)
    if sessione is None:
        raise HTTPException(status_code=404, detail="Sessione scaduta: avvia una nuova conversazione.")
    sessione.ultimo_uso = time.time()

    if sessione.fase == "registrazione":
        return {"reply": gestisci_registrazione(sessione, richiesta.text), "phase": sessione.fase}

    anonimo = sessione.anonimizzatore.anonimizza(richiesta.text)
    try:
        risposta = chiedi_al_be(sessione, anonimo)
    except RuntimeError as errore:
        raise HTTPException(status_code=502, detail=str(errore))
    return {"reply": sessione.anonimizzatore.ripristina(risposta), "phase": sessione.fase}
