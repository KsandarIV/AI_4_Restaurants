# FLUSSO — come gira il progetto (una pagina per capirlo tutto)

Rete: 3 PC sulla stessa LAN (`10.10.x`). Solo HTTP/WebSocket tra macchine, mai import di codice altrui.

```
                        ┌───────────── PC-BE (fulcro, parte per primo) ─────────────┐
                        │ :8000  backend/main.py                                     │
                        │   API + LangGraph + SQLite + Ollama gemma4:12b            │
                        │ :8080  sito vetrina (frontend/ statico)                   │
                        └───────┬───────────────────────────────┬───────────────────┘
                                │                               │
              POST /api/chat,   │                               │  GET /api/menu|info
              /api/chat/stream, │                               │  availability,
              CRUD reservations │                               │  customers
                                ▼                               ▼
   ┌──────── PC-CHAT ────────┐                    ┌──────── PC-VOICE ────────┐
   │ :8501 Streamlit (UI)    │                    │ :8003 voicebot v1        │
   │ :8002 chat/api.py       │                    │   VAD→STT→LLM(BE)→TTS    │
   │   (il sito sul BE       │                    │   WS /ws/voice + barge-in│
   │    chiama QUI, mai      │                    │ :8003 /test-voice        │
   │    diretto al BE)       │                    │   pagina test microfono  │
   └─────────────────────────┘                    │ v2 on-demand (mic locale │
                                                  │   via sounddevice, ovunque)│
                                                  └────────────────────────────┘
```

## Flusso per macchina (ordine d'accensione irrilevante: chat/voice attendono il BE)

| # | Macchina | Comando | Fa |
|---|---|---|---|
| 1 | BE | `python entrypoint\avvia.py` (ruolo be) | venv base+be → `.env` → firewall 8000/8080 → `backend.main` + sito :8080 |
| 2 | CHAT | `python entrypoint\avvia.py` (ruolo chat) | attende BE → venv base+chat (+spacy) → Streamlit :8501 + api :8002 |
| 3 | VOICE | `python entrypoint\avvia.py` (ruolo voice) | attende BE → venv base+voice (+Piper) → voicebot :8003 |
| 4 | Presentatore (qualsiasi PC) | `python entrypoint\avvia.py --attendi` | aspetta TUTTO OK, poi demo |

## Flusso voce v1 (real-time, WebSocket)

Browser/mic → PCM16LE 16 kHz → `ws://VOICE:8003/ws/voice` → VAD → STT whisper →
`POST /api/chat/stream` SSE → token → TTS Piper per-frase → PCM al browser.
Barge-in: voce > `BARGE_IN_MIN_MS` mentre il bot parla cancella il turno (`{"event":"barge_in"}`).
Identico alla chat: il bot parla per primo e chiede nome+telefono (fase di registrazione, solo
`POST /api/customers`, mai l'LLM), poi ogni frase passa da anonimizza → BE → ripristina.
Dal PC con microfono senza browser: `python -m voicebot.live_client ws://VOICE:8003/ws/voice`.
Se qualcosa non va: `python -m voicebot.doctor` (o `http://VOICE:8003/diag`).
Sito: `http://VOICE:8003/` (stesso aspetto del sito chat: menu, orari, assistente vocale e
**Le mie prenotazioni** con lo stato aggiornato dal BE). A fine prenotazione/modifica/cancellazione il
bot rilegge a voce il riepilogo (dati veri dal BE, `GET /api/reservations/{codice}`) e chiede un ultimo sì.
Comandi: test locale con BE finto `voice\voice local`; flusso reale a tre macchine `python entrypoint\avvia.py`.

## Flusso voce v2 (on-demand, come la chat)

Mic locale (sounddevice, niente browser) → STT → conversazione identica alla chat
(registrazione, anonimizza, `POST /api/chat` sincrono) → risposta completa → TTS → altoparlante.
Gira su **qualsiasi PC** (anche BE/presentatore): il mic è sempre quello locale al processo.
Con `CHAT_SERVICE_URL=http://CHAT:8002` appoggia invece il servizio `chat/api.py` (il chatbot
lavora "sotto", invisibile): `python -m voicebot.v2` (`--text` per provare da tastiera).

## Flusso chat (sito + Streamlit)

Sito (dal BE :8080) → `POST CHAT:8002/chat/session|message` → anonimizza →
`POST BE:8000/api/chat` → risposta → ripristina segnaposto → browser.
Streamlit :8501 = stessa logica in UI autonoma.

## Limite noto browser (non nostro): il microfono via `getUserMedia` funziona solo
da `localhost`/HTTPS. Da LAN-IP il browser lo blocca: per la voce da altre macchine
usare la v2 (mic locale, nessun browser) o aprire la pagina di test in localhost
sulla macchina voice.
