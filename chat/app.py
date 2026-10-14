"""Chatbot testuale per la prenotazione di un tavolo (componente CHAT).

Avvio:  streamlit run app.py
Il BE si raggiunge solo via rete: indirizzo in barra laterale o variabile BE_URL.

Flusso per ogni messaggio dell'utente:
    testo -> anonimizza -> POST /api/chat sul BE -> risposta -> ripristina -> mostra
"""
import os
import uuid

import requests
import streamlit as st

from anonimizzatore import Anonimizzatore

BE_URL_PREDEFINITO = os.getenv("BE_URL", "http://localhost:8000")
TIMEOUT_SECONDI = 120  # l'LLM locale può essere lento

st.set_page_config(page_title="Prenota un tavolo", page_icon="🍝")


def nuova_conversazione():
    """Azzera lo stato: nuova sessione, nuovo cliente anonimo, nuova mappa dei segnaposto."""
    st.session_state.messaggi = []  # ogni voce: {"ruolo", "testo", "inviato"}
    st.session_state.session_id = f"chat_{uuid.uuid4().hex[:8]}"
    st.session_state.customer_id = f"anon_{uuid.uuid4().hex[:6]}"
    st.session_state.anonimizzatore = Anonimizzatore()


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
    except requests.ConnectionError:
        raise RuntimeError("Non riesco a raggiungere il server. Controlla che il BE sia acceso e l'indirizzo sia corretto.")
    except requests.Timeout:
        raise RuntimeError("Il server ci sta mettendo troppo a rispondere. Riprova tra poco.")
    if risposta.status_code != 200:
        raise RuntimeError(f"Il server ha risposto con un errore ({risposta.status_code}).")
    try:
        return risposta.json()["reply"]
    except (ValueError, KeyError):
        raise RuntimeError("Risposta del server in un formato inatteso.")


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

for m in st.session_state.messaggi:
    with st.chat_message(m["ruolo"]):
        st.write(m["testo"])
        if mostra_be and m["ruolo"] == "user":
            st.caption(f"Inviato al BE: {m['inviato']}")

domanda = st.chat_input("Scrivi qui il tuo messaggio...")
if domanda:
    anonimo = st.session_state.anonimizzatore.anonimizza(domanda)
    st.session_state.messaggi.append({"ruolo": "user", "testo": domanda, "inviato": anonimo})
    with st.chat_message("user"):
        st.write(domanda)
        if mostra_be:
            st.caption(f"Inviato al BE: {anonimo}")

    with st.chat_message("assistant"):
        try:
            with st.spinner("Sto scrivendo..."):
                risposta = chiedi_al_be(be_url, anonimo)
            risposta = st.session_state.anonimizzatore.ripristina(risposta)
            st.write(risposta)
            st.session_state.messaggi.append({"ruolo": "assistant", "testo": risposta, "inviato": ""})
        except RuntimeError as errore:
            st.error(str(errore))
