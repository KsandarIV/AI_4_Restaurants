# Voice-bot — prenotazione tavolo al ristorante (Traccia 3, membro VOICE)

Pipeline audio real-time full-duplex: browser/mic → WebSocket → VAD → STT → LLM (sul BE) → TTS → WebSocket.
Tutti i modelli girano in **locale**; il BE (macchina separata in LAN, con LLM + SQLite) è raggiunto solo via HTTP.

## Architettura file

```
voice/
├── pyproject.toml              # packaging per editable install + config pytest/mypy/ruff
├── src/voicebot/
│   ├── __main__.py             # entrypoint uvicorn (graceful shutdown)
│   ├── config.py               # Settings pydantic (env/BACKEND_*, VAD/STT/TTS, code)
│   ├── logging_json.py         # logging strutturato JSON
│   ├── audio.py                # AudioFrame, RMS, split_sentences
│   ├── interfaces.py           # AbstractVAD/STT/LLMOrchestrator/TTS
│   ├── vad.py                  # EnergyVAD (default, zero-dep) + WebRtcVADWrapper + factory
│   ├── stt.py                  # FasterWhisperSTT (locale) + FakeSTT + factory
│   ├── tts.py                  # PiperTTS streaming per-frase + FakeTTS + factory
│   ├── pii.py                  # scrub PII (email/tel/CF/carte) prima dell'invio al BE
│   ├── backend.py              # BackendClient httpx: retry/backoff, timeout, stream SSE, tool REST
│   ├── orchestrator.py         # BackendOrchestrator: history, shortcut menu/info/disponibilità, token streaming
│   └── pipeline/
│       ├── session.py          # ★ core loop: 3 task asyncio + asyncio.Queue + barge-in (generation counter)
│       └── server.py           # FastAPI: /health, /ready, /ws/voice (reader/writer, idle-timeout, close graceful)
└── tests/
    ├── test_units.py           # VAD, PII, audio helpers
    └── test_pipeline.py        # turno completo + barge-in + history trim (fake STT/TTS, no rete)
```

## Core loop (producer-consumer)

- **Producer:** reader WebSocket → `audio_in_q: Queue[bytes]` (PCM16 16 kHz, 20 ms). Queue bounded → backpressure.
- **VAD loop:** `process_frame` in `to_thread` → `speech_start`/`speech_end`; se `speaking_event` è attivo → `_handle_barge_in()`.
- **STT loop:** segmenti → `transcribe` con timeout 30 s → `text_q`.
- **LLM loop:** per turno, `pump_tokens` riempie `token_q` mentre `tts.synthesize_stream` emette audio in `audio_out_q`. Streaming reale: l'audio parte prima che l'LLM finisca.
- **Barge-in:** contatore `_gen` invalida il turno corrente, svuota `audio_out_q`, `vad.reset()`, invia `{"event":"barge_in"}`.
- **Shutdown:** `close()` invia poison-pill `None`, cancella i task, `await ... timeout=5s`, chiude STT/TTS/BE.

## Contratto BE reale (da `backend/api/routes.py`, mount `/api` + root)

| Metodo | Path | Uso |
|---|---|---|
| GET | `/health`, `/api/health` | readiness |
| POST | `/api/chat` | chat sincrona `{message, session_id, customer_id, client_type}` |
| POST | `/api/chat/stream` | SSE `data: {"token"}` … `data: [DONE]` (parola-a-parola dopo inferenza completa) |
| GET | `/api/availability?date&time&party_size` | verifica disponibilità |
| POST | `/api/reservations` | prenota (caso 1) |
| GET | `/api/reservations/{booking_code}` | stato prenotazione |
| PATCH/PUT | `/api/reservations/{booking_code}` | modifica (caso 2) |
| DELETE | `/api/reservations/{booking_code}` | cancella (caso 3) |
| GET | `/api/menu` | caso d'uso 4 (filtri categoria/allergeni/diete) |
| GET | `/api/info[?key=]` | caso d'uso 5 (posizione/contatti) |

Il `BackendClient` invia `session_id`/`customer_id` anonimo/`client_type="voice"` sullo
stream così la memoria LangGraph del BE funziona tra i turni. Porta BE di default: **8000**.

## Protocollo WebSocket `/ws/voice`

- Client→server: frame binari PCM16LE mono 16 kHz/20 ms · `{"cmd":"eos"}` · `{"cmd":"reset"}`
- Server→client: frame binari PCM16 (risposta) · `{"event":"ready"}` · `{"event":"barge_in"}`
- Riconnessione: lato client con backoff esponenziale (il server è stateless per connessione).

## Avvio locale (venv condiviso)

```bat
REM dalla root del repo, prima volta: setup guidato (venv + modelli locali)
python setup\setup_env.py
copy .env.example .env
REM poi imposta BACKEND_BASE_URL con l'IP LAN del BE

REM avvio voice con il venv condiviso (dalla root)
.venv\Scripts\python -m voicebot   # ws://localhost:8003/ws/voice
```

Senza modelli (CI/demo): `STT_BACKEND=fake TTS_BACKEND=fake` nel `.env`.
Il `.env` è unico in root (`config.find_env_file` lo cerca anche lanciando da `voice/`).

## Test

```bat
REM dalla cartella voice, con il venv condiviso
..\.venv\Scripts\python -m pytest tests -q   # 7 test, nessun modello/rete richiesto
```

## Vincoli traccia — dove sono rispettati

1. Macchine diverse: VOICE è un servizio autonomo, parla al BE solo via `BACKEND_BASE_URL` (LAN).
2. Rete: solo HTTP/SSE + WebSocket; nessuna importazione di codice BE.
3. PII: `pii.scrub_pii` applicato a ogni messaggio prima dell'invio (`backend.stream_chat`).
4. Modelli locali: faster-whisper / webrtcvad / Piper di default; nessun provider cloud nel codice.
