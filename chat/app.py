"""Chatbot testuale per la prenotazione di un tavolo (componente CHAT).

Avvio:  streamlit run app.py
Il BE si raggiunge solo via rete: indirizzo in barra laterale o variabile BE_URL.

Due fasi:
1. registrazione: il bot chiede in un solo messaggio nome e telefono (contatti.py). Questi
   dati vanno solo a POST /api/customers, che risponde con un customer_id anonimo.
   L'LLM non li vede mai.
2. chat: per ogni messaggio  testo -> anonimizza -> POST /api/chat -> ripristina -> mostra,
   usando quel customer_id.
"""
import os
import uuid

import requests
import streamlit as st

from anonimizzatore import Anonimizzatore
from contatti import MESSAGGIO_INIZIALE, Registrazione

BE_URL_PREDEFINITO = os.getenv("BE_URL", "http://localhost:8000")
TIMEOUT_SECONDI = 120  # l'LLM locale può essere lento
MESSAGGIO_BENVENUTO = (
    "Registrazione completata. Come posso aiutarla? Posso prenotare, modificare o cancellare un tavolo, "
    "mostrarle il menu o darle informazioni sul locale."
)

st.set_page_config(page_title="Prenota un tavolo", page_icon="🍝")


def nuova_conversazione():
    """Azzera lo stato: nuova sessione, nuovo cliente, nuova mappa dei segnaposto."""
    st.session_state.messaggi = [{"ruolo": "assistant", "testo": MESSAGGIO_INIZIALE, "inviato": ""}]
    st.session_state.session_id = f"chat_{uuid.uuid4().hex[:8]}"
    st.session_state.customer_id = f"anon_{uuid.uuid4().hex[:6]}"  # sostituito da quello del BE a registrazione fatta
    st.session_state.anonimizzatore = Anonimizzatore()
    st.session_state.registrazione = Registrazione()
    st.session_state.fase = "registrazione"  # poi "chat"


def _errore_di_rete(errore):
    if isinstance(errore, requests.Timeout):
        return RuntimeError("Il server ci sta mettendo troppo a rispondere. Riprova tra poco.")
    return RuntimeError("Non riesco a raggiungere il server. Controlla che il BE sia acceso e l'indirizzo sia corretto.")


def registra_cliente(be_url, nome, telefono):
    """Invia nome e telefono al BE e restituisce il customer_id anonimo che il BE assegna."""
    payload = {"name": nome, "phone": telefono, "consent": True}
    try:
        risposta = requests.post(f"{be_url.rstrip('/')}/api/customers", json=payload, timeout=30)
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


def chiedi_al_be(be_url, testo_anonimo):
    """Invia il messaggio al BE e restituisce il testo della risposta.

    Solleva RuntimeError con un messaggio comprensibile se qualcosa va storto.
    """
    payload = {
        "message": testo_anonimo,
        "session_id": st.session_state.session_id,
        "customer_id": st.session_state.customer_id,
        "client_type": "chat",
    }
    try:
        risposta = requests.post(f"{be_url.rstrip('/')}/api/chat", json=payload, timeout=TIMEOUT_SECONDI)
    except (requests.ConnectionError, requests.Timeout) as errore:
        raise _errore_di_rete(errore)
    if risposta.status_code != 200:
        raise RuntimeError(f"Il server ha risposto con un errore ({risposta.status_code}).")
    try:
        return risposta.json()["reply"]
    except (ValueError, KeyError):
        raise RuntimeError("Risposta del server in un formato inatteso.")


def gestisci_registrazione(domanda, be_url):
    """Un passo del dialogo di registrazione. Restituisce la risposta del bot."""
    registrazione = st.session_state.registrazione
    risposta, azione = registrazione.gestisci(domanda)
    if azione == "registra":
        try:
            with st.spinner("Registro i dati..."):
                st.session_state.customer_id = registra_cliente(be_url, registrazione.nome, registrazione.telefono)
            st.session_state.fase = "chat"
            risposta = f"Grazie {registrazione.nome}! {MESSAGGIO_BENVENUTO}"
        except RuntimeError as errore:
            registrazione.fase = "conferma"  # i dati restano: basta riscrivere "sì" per riprovare
            risposta = f"{errore} Quando vuole, scriva sì per riprovare."
    elif azione == "rinuncia":
        st.session_state.fase = "chat"  # prosegue con il customer_id anonimo
    return risposta


if "messaggi" not in st.session_state:
    nuova_conversazione()

# ---------- Barra laterale ----------
with st.sidebar:
    st.header("Impostazioni")
    be_url = st.text_input("Indirizzo del BE", BE_URL_PREDEFINITO)
    mostra_be = st.checkbox("Mostra cosa vede il BE", help="Utile in demo: mostra il testo già anonimizzato.")
    if st.button("Verifica connessione"):
        try:
            r = requests.get(f"{be_url.rstrip('/')}/api/health", timeout=5)
            st.success("BE raggiungibile") if r.ok else st.error(f"BE risponde con errore {r.status_code}")
        except requests.RequestException:
            st.error("BE non raggiungibile")
    if st.button("Nuova conversazione"):
        nuova_conversazione()
        st.rerun()

# ---------- Chat ----------
st.title("🍝 Prenota un tavolo")
st.caption("Puoi prenotare, modificare o cancellare una prenotazione, vedere il menu e chiedere informazioni.")

NOTA_CONTATTI = "Dati di contatto: vanno solo all'endpoint clienti del BE, non all'LLM."


def mostra_messaggio(ruolo, testo, inviato):
    with st.chat_message(ruolo):
        st.write(testo)
        if mostra_be and ruolo == "user":
            st.caption(NOTA_CONTATTI if inviato is None else f"Inviato al BE: {inviato}")


for m in st.session_state.messaggi:
    mostra_messaggio(m["ruolo"], m["testo"], m["inviato"])

domanda = st.chat_input("Scrivi qui il tuo messaggio...")
if domanda:
    if st.session_state.fase == "registrazione":
        inviato = None  # in questa fase il testo non passa né dall'anonimizzatore né dall'LLM
    else:
        inviato = st.session_state.anonimizzatore.anonimizza(domanda)
    st.session_state.messaggi.append({"ruolo": "user", "testo": domanda, "inviato": inviato})
    mostra_messaggio("user", domanda, inviato)

    with st.chat_message("assistant"):
        if st.session_state.fase == "registrazione":
            risposta = gestisci_registrazione(domanda, be_url)
            st.write(risposta)
            st.session_state.messaggi.append({"ruolo": "assistant", "testo": risposta, "inviato": ""})
        else:
            try:
                with st.spinner("Sto scrivendo..."):
                    risposta = chiedi_al_be(be_url, inviato)
                risposta = st.session_state.anonimizzatore.ripristina(risposta)
                st.write(risposta)
                st.session_state.messaggi.append({"ruolo": "assistant", "testo": risposta, "inviato": ""})
            except RuntimeError as errore:
                st.error(str(errore))
