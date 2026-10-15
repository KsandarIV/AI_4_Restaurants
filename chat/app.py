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
import html
import os
import re
import uuid

import requests
import streamlit as st

from anonimizzatore import Anonimizzatore
from contatti import MESSAGGIO_INIZIALE, Registrazione

def _be_url_da_env() -> str:
    """BE_URL dall'ambiente; se manca, dal file .env di progetto; altrimenti localhost."""
    if os.getenv("BE_URL"):
        return os.environ["BE_URL"]
    try:
        with open(os.path.join(os.path.dirname(__file__), "..", ".env"), encoding="utf-8") as f:
            for riga in f:
                if riga.startswith("BE_URL="):
                    return riga.split("=", 1)[1].strip()
    except OSError:
        pass
    return "http://localhost:8000"


BE_URL_PREDEFINITO = _be_url_da_env()
TIMEOUT_SECONDI = 120  # l'LLM locale può essere lento
MESSAGGIO_BENVENUTO = (
    "Registrazione completata. Come posso aiutarla? Posso prenotare, modificare o cancellare un tavolo, "
    "mostrarle il menu o darle informazioni sul locale."
)

st.set_page_config(page_title="Prenota un tavolo", page_icon="🍝")

# Stesso aspetto del sito (frontend/css/style.css): crema, rosso mattone, Georgia.
STILE = """
<style>
:root { --bg:#fffaf3; --surface:#ffffff; --text:#2b211b; --muted:#6e5f55; --accent:#b3341f;
        --accent-dark:#8a2615; --line:#eadfce; --bot:#f4ece0; }
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
  background: var(--bg) !important; color: var(--text) !important; font-family: Georgia, "Times New Roman", serif; }
[data-testid="stHeader"] { background: rgba(255,250,243,.95) !important; border-bottom: 1px solid var(--line); }
[data-testid="stHeader"] * { color: var(--muted) !important; }
h1, h2, h3, .stMarkdown h1, .stMarkdown h2 { font-family: Georgia, serif !important; color: var(--accent) !important; }
p, label, span, li { color: var(--text); }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * { color: var(--muted) !important; }

/* barra laterale */
[data-testid="stSidebar"] { background: var(--surface) !important; border-right: 1px solid var(--line); }
[data-testid="stSidebar"] h2 { font-size: 1.5rem; margin-bottom: .2rem; }
[data-testid="stSidebar"] label, [data-testid="stSidebar"] p { font-family: system-ui, sans-serif; font-size: .9rem; }
.sez { font-family: system-ui, sans-serif; text-transform: uppercase; letter-spacing: .08em; font-size: .75rem;
       color: var(--muted); font-weight: 600; margin: 1.1rem 0 .4rem; }
.stato { font-family: system-ui, sans-serif; font-size: .8rem; color: var(--muted); }
.stato b.ok { color: #2e8b57; } .stato b.ko { color: var(--accent); }
.stato code { background: #fde9d4; color: var(--accent-dark); border-radius: 6px; padding: 0 4px; }

/* campi e pulsanti */
[data-testid="stTextInput"] input {
  background: var(--surface) !important; color: var(--text) !important; border: 1px solid var(--line) !important;
  border-radius: 999px !important; font-family: system-ui, sans-serif; }
[data-testid="stChatInput"] textarea { background: transparent !important; color: var(--text) !important;
  font-family: system-ui, sans-serif; }
[data-testid="stTextInput"] input:focus { border-color: var(--accent) !important; box-shadow: none !important; }
[data-testid="stBaseButton-secondary"] { font-family: system-ui, sans-serif; font-weight: 600; background: var(--surface);
  color: var(--accent); border: 2px solid var(--accent); border-radius: 999px; }
[data-testid="stBaseButton-secondary"]:hover { background: var(--accent); color: #fff; border-color: var(--accent); }
[data-baseweb="checkbox"]:has(input:checked) > div:first-child { background: var(--accent) !important; border-color: var(--accent) !important; }
[data-testid="stAlert"] { border-radius: 12px; font-family: system-ui, sans-serif; }

/* chat */
[data-testid="stChatMessage"] { background: var(--bot) !important; border-radius: 16px; padding: .7rem 1rem; margin-bottom: .6rem; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { background: var(--accent) !important; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) p { color: #fff !important; }
[data-testid="stBottom"], [data-testid="stBottom"] > div { background: var(--bg) !important; }
[data-testid="stChatInput"], [data-testid="stChatInput"] > div { background: var(--surface) !important; border-color: var(--line) !important; border-radius: 24px; }

/* confronto: cosa scrive l'utente / cosa legge l'LLM */
.conf { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: .6rem; font-family: system-ui, sans-serif; }
.conf > div { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 8px 10px;
              font-size: .82rem; color: var(--text); }
.conf .tit { text-transform: uppercase; letter-spacing: .06em; font-size: .68rem; font-weight: 700; margin-bottom: 3px; }
.conf .tu .tit { color: var(--muted); } .conf .llm .tit { color: #2e8b57; }
.conf .nolleg { grid-column: 1 / -1; background: #fdecea; border-color: #f3c6bf; }
.conf .nolleg .tit { color: var(--accent-dark); }
.conf code { background: #fde9d4; color: var(--accent-dark); border-radius: 6px; padding: 0 4px; }
@media (max-width: 720px) { .conf { grid-template-columns: 1fr; } }
</style>
"""
st.markdown(STILE, unsafe_allow_html=True)


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
    st.markdown('<div class="sez">Collegamento</div>', unsafe_allow_html=True)
    be_url = st.text_input("Indirizzo del BE", BE_URL_PREDEFINITO)
    if st.button("Verifica connessione", use_container_width=True):
        try:
            r = requests.get(f"{be_url.rstrip('/')}/api/health", timeout=5)
            st.session_state.stato_be = "ok" if r.ok else f"errore {r.status_code}"
        except requests.RequestException:
            st.session_state.stato_be = "ko"
    stato = st.session_state.get("stato_be")
    if stato == "ok":
        st.markdown('<div class="stato"><b class="ok">●</b> BE raggiungibile</div>', unsafe_allow_html=True)
    elif stato:
        testo = "BE non raggiungibile" if stato == "ko" else f"BE risponde con {stato}"
        st.markdown(f'<div class="stato"><b class="ko">●</b> {testo}</div>', unsafe_allow_html=True)

    st.markdown('<div class="sez">Privacy</div>', unsafe_allow_html=True)
    mostra_be = st.checkbox(
        "Confronta: tu / LLM",
        help="Sotto ogni tuo messaggio mostra cosa hai scritto e cosa legge davvero l'LLM, già anonimizzato.",
    )
    if mostra_be:
        st.markdown(
            '<div class="stato">Nome e telefono della registrazione vanno solo all\'endpoint clienti del BE. '
            "Poi ogni messaggio passa dall'anonimizzatore: i dati personali diventano segnaposto "
            "<code>[TELEFONO_1]</code>, <code>[NOME_1]</code>… e tornano veri solo nella risposta che vedi tu.</div>",
            unsafe_allow_html=True,
        )

    st.markdown('<div class="sez">Conversazione</div>', unsafe_allow_html=True)
    if st.button("Nuova conversazione", use_container_width=True):
        nuova_conversazione()
        st.rerun()

# ---------- Chat ----------
st.title("🍝 Prenota un tavolo")
st.caption("Puoi prenotare, modificare o cancellare una prenotazione, vedere il menu e chiedere informazioni.")

SEGNAPOSTO = re.compile(r"\[[A-Z_]+_\d+\]")


def confronto(scritto, inviato):
    """Due riquadri affiancati: cosa ha scritto l'utente e cosa legge l'LLM."""
    if inviato is None:
        return (
            '<div class="conf"><div class="nolleg"><div class="tit">L\'LLM non legge questo messaggio</div>'
            "Dati di contatto: vanno solo all'endpoint clienti del BE.</div></div>"
        )
    nota = "" if inviato != scritto else "<br><i>Nessun dato personale da nascondere: testo identico.</i>"
    llm = SEGNAPOSTO.sub(lambda m: f"<code>{m.group(0)}</code>", html.escape(inviato))
    return (
        '<div class="conf">'
        f'<div class="tu"><div class="tit">Hai scritto</div>{html.escape(scritto)}</div>'
        f'<div class="llm"><div class="tit">Legge l\'LLM</div>{llm}{nota}</div>'
        "</div>"
    )


def mostra_messaggio(ruolo, testo, inviato):
    with st.chat_message(ruolo):
        st.write(testo)
        if mostra_be and ruolo == "user":
            st.markdown(confronto(testo, inviato), unsafe_allow_html=True)


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
