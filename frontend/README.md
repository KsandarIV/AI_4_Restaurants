# Sito della Trattoria Bella Napoli (frontend)

Sito statico (HTML, CSS, JavaScript semplice: nessuna build, nessun npm) con menu, orari, dove siamo, contatti e un assistente per prenotare **scrivendo o parlando**.

```
Browser (frontend/)
  ├─ menu, orari, info ──────────► BE     :8000  GET /api/menu, /api/info, /api/health
  ├─ scheda "Scrivi" ────────────► CHAT   :8002  POST /chat/session, /chat/message   (chat/api.py → BE)
  └─ scheda "Parla" ─────────────► VOICE  :8003  WebSocket /ws/voice
```

La chat non passa mai dal browser al BE: passa da [chat/api.py](../chat/api.py), che usa `anonimizzatore.py` e `contatti.py` (la stessa logica della versione Streamlit `chat/app.py`) per anonimizzare e registrare il cliente.

## Avvio

Una volta, nell'ambiente `chatbot_ristorante`: `pip install -r chat/requirements.txt`. Poi, in quattro terminali dalla radice del progetto:

```bash
# 1. BE                                        porta 8000
python -m backend.main
# 2. CHAT per il sito (dalla cartella chat/)   porta 8002   (BE_URL se il BE è su un'altra macchina)
cd chat && python -m uvicorn api:app --host 0.0.0.0 --port 8002
# 3. VOICE                                     porta 8003
.venv\Scripts\python -m voicebot
# 4. il sito
python -m http.server 8080 --directory frontend
```

Aprire **http://localhost:8080**. Il microfono funziona solo su pagina "sicura": `http://localhost` va bene, `http://192.168.x.x:8080` no (il browser lo blocca). In LAN usare il sito dal PC che lo ospita o servirlo in HTTPS.

Se il BE è spento il sito resta visibile con testi di riserva e l'assistente avvisa che il server non è raggiungibile.

## Cosa modificare quando cambia un componente

| Cambia… | Cosa | File |
|---|---|---|
| Indirizzo o porta di BE, CHAT o VOICE | gli URL | `frontend/js/config.js` (**unico** punto che li contiene) |
| Path di menu, info, health del BE | i path | `frontend/js/config.js` → `be` |
| Formato dei piatti del BE | come si mostrano | `frontend/js/site.js` → `renderMenu`, `tags` |
| Chiavi delle informazioni del BE | gli attributi `data-info="..."` | `frontend/index.html` |
| Contratto del CHAT (path, JSON) | path e corpo | `config.js` → `chat` e `frontend/js/chat.js` |
| Logica della chat (registrazione, anonimizzazione, chiamata al BE) | tutta in Python | `chat/api.py`, `chat/contatti.py`, `chat/anonimizzatore.py`: il sito non si tocca |
| Protocollo audio del VOICE | frequenze, eventi | `config.js` → `voice` e `frontend/js/voice.js` |
| Grafica e testi | | `frontend/css/style.css` (colori in `:root`), `frontend/index.html` |
| Endpoint dell'area staff del BE | path e campi | `config.js` → `be.staffPath` e `frontend/js/staff.js` (unico file che parla con l'area staff) |

## Area ristoratore (`staff.html`)

Link "Area ristoratore" nel piè di pagina del sito, oppure direttamente `http://localhost:8080/staff.html`. Si entra con la chiave `STAFF_API_KEY` del `.env` del BE (si genera con `python -m backend.maintenance staff-key`); la chiave resta solo nella scheda del browser e sparisce alla chiusura (o con "Esci").

Tre schede:
- **Prenotazioni**: elenco con nome e telefono del cliente, filtro per data e stato, totale coperti; **Modifica** (data, ora, persone, note) e **Cancella**. Se non c'è un tavolo libero il BE rifiuta la modifica e il motivo compare nella finestra.
- **Chiusure**: chiude o riapre il locale in una data. Le prenotazioni già fatte non vengono cancellate: la pagina le elenca.
- **Menu**: segna un piatto come esaurito o di nuovo disponibile.

Richiede nel BE gli endpoint `/api/staff/...` (anche `PATCH`/`DELETE` delle prenotazioni e `GET /api/staff/menu`, aggiunti con questa pagina). Il BE deve accettare richieste da altri indirizzi (CORS già aperto) e la porta del BE raggiungibile dal browser.
Attenzione: nome e telefono dei clienti viaggiano in HTTP non cifrato; usare l'area solo sulla rete locale.

Ogni componente ha **un solo file JS** che lo conosce (`site.js` BE, `chat.js` CHAT, `voice.js` VOICE); `assistant.js` gestisce solo la finestra.

## Contratti usati

**CHAT** (`chat/api.py`)
- `POST /chat/session` → `{session_id, phase, reply}`
- `POST /chat/message` `{session_id, text}` → `{reply, phase}`; `404` sessione scaduta, `502` BE non raggiungibile.

**VOICE**: invia frame binari PCM16 mono 16 kHz da 20 ms; riceve PCM16 alla frequenza del TTS (`outputSampleRate` in `config.js`, 22050; se il voice mette `tts_sample_rate` nell'evento `ready` vale quello); eventi JSON `ready` e `barge_in`.

## Limiti noti

- La modalità vocale non è stata provata con il VOICE reale (mancavano i modelli Whisper e Piper): da verificare con il collega. Se la voce sembra accelerata o rallentata, correggere `outputSampleRate`.
- Il voicebot non registra il cliente (`/api/customers`): con la registrazione attiva nel BE le prenotazioni a voce vengono rifiutate finché non viene adattato.
- Le sessioni del CHAT sono in memoria: un riavvio le perde.
- La mappa è OpenStreetMap con coordinate approssimate di Via Toledo.
