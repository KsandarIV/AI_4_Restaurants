# FLUSSO — come gira il progetto (una pagina per capirlo tutto)

Rete: 3 PC sulla stessa LAN (`10.10.x`). Solo HTTP/WebSocket tra macchine, mai import di codice altrui.

```
                        ┌───────────── PC-BE (fulcro, parte per primo) ─────────────┐
                        │ :8000  backend/main.py                                     │
                        │   API + LangGraph + SQLite + Ollama gemma4:12b            │
                        │ :8080  sito vetrina (frontend/ statico)                   │
                        │ :8090  GATEWAY https: sito completo + reverse proxy       │
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
| 1 | BE | `python entrypoint\avvia.py` (ruolo be) | venv base+be → `.env` → firewall 8000/8080/8090 → `backend.main` + sito :8080 + gateway :8090 → apre i siti |
| 2 | CHAT | `python entrypoint\avvia.py` (ruolo chat) | attende BE → venv base+chat (+spacy) → Streamlit :8501 + api :8002 + sito :8080 → si annuncia al gateway → apre i siti |
| 3 | VOICE | `python entrypoint\avvia.py` (ruolo voice) | attende BE → venv base+voice (+Piper) → voicebot :8003 → si annuncia al gateway → apre i siti |
| 4 | Presentatore (qualsiasi PC) | `python entrypoint\avvia.py --attendi` | aspetta TUTTO OK, poi demo |

## Flusso voce v1 (real-time, WebSocket)

Browser/mic → PCM16LE 16 kHz → `ws://VOICE:8003/ws/voice` (o `wss://BE:8090/voice/ws/voice` dal sito completo) → VAD → STT whisper →
`POST /api/chat/stream` SSE → token → TTS Piper per-frase → PCM al browser.
Barge-in: voce > `BARGE_IN_MIN_MS` mentre il bot parla cancella il turno (`{"event":"barge_in"}`).
Identico alla chat, nell'ordine di una telefonata vera: il bot apre con un saluto e **non chiede nulla**; solo quando il cliente parla di prenotare chiede nome+telefono
(fase di registrazione, solo `POST /api/customers`, mai l'LLM), poi **rimanda al BE la richiesta già detta** (così non va ripetuta) e ogni frase passa da anonimizza → BE → ripristina.
A fine prenotazione/modifica/cancellazione il bot rilegge a voce il riepilogo (dati veri dal BE, `GET /api/reservations/{codice}`) e chiede un ultimo sì.
Il contesto dell'LLM si rinfresca dopo 20 scambi senza prenotazione (3 volte al massimo, poi la chiamata si chiude con garbo).
Dal PC con microfono senza browser: `python -m voicebot.live_client ws://VOICE:8003/ws/voice`.
Se qualcosa non va: `python -m voicebot.doctor` (o `http://VOICE:8003/diag`, scheda STATO della pagina di test).
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

## Microfono e HTTPS (risolto dal gateway)

Il microfono (`getUserMedia`) funziona solo in un *secure context*: `localhost`, `*.localhost` o qualsiasi `https://`. Da `http://192.168.x.x` il browser lo blocca.
Per questo il sito completo è servito dal **gateway sul BE in HTTPS** (`https://<IP-BE>:8090`, certificato autofirmato: "Avanzate → Procedi" una volta per browser) e
sul BE anche come `https://completo.localhost:8090`. La pagina di test voce si apre su `http://voce.localhost:8003/test-voice` (stessa macchina → sicuro).
Dettagli: `showcase/README.md`.

## Materiale di studio e presentazione (voice)

`docs/studio/voice/`: `MANUALE_TECNICO.md` (comandi per componente, test, sessioni live, **configurazioni di avvio** a tre macchine e alternative),
`PRESENTAZIONE.md` (copione passo per passo), `flowchart_flusso_codice.svg` (flowchart verticale: avvio → chiamata → chiusura) e le mini-presentazioni PDF.

## Siti della demo (si aprono da soli con `python entrypoint\avvia.py`) — dettagli in `showcase/README.md`, elenco con link in `docs/SITI.md`

Topologia a stella: **CHAT e VOICE non si parlano mai**, tutto passa dal gateway sul BE.

```
 browser di qualsiasi PC --HTTPS--> gateway BE :8090 --+--> BE      :8000  /api/*, /docs  (database, area ristoratore)
                                                        +--> VOICE   :8003  /voice/*, WebSocket /voice/ws/voice
                                                        '--> CHAT    :8002  /voice/site/chat/*  (la finestrella chat)
```

| Macchina | Si apre | Cosa |
|---|---|---|
| BE | `http://solo-be.localhost:8080/` | sito senza chat/voce funzionanti (compaiono in basso a destra) |
| BE | `https://completo.localhost:8090/` | sito **completo**: chat, voce, prenotazioni, area ristoratore, Swagger |
| CHAT | `http://chat.localhost:8080/` + `https://<IP-BE>:8090/` | il sito di `frontend/` con la chat (parte da solo) + il sito completo del BE |
| VOICE | `http://voce.localhost:8003/test-voice` + `https://<IP-BE>:8090/` | pagina di test voce (orb, schede STATO e TECNICA) + il sito completo del BE |

CHAT e VOICE si **annunciano** al gateway (`POST /register`) e il BE ne verifica l'indirizzo con la firma del servizio: gli IP di esempio di `lan/lan_config.json` non vengono mai creduti.
