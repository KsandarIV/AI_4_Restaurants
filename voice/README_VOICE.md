# Voice bot — table booking for the restaurant (Traccia 3, VOICE member)

The voice bot is the **chat bot with ears and a mouth**: same registration dialogue, same
anonymisation, same BE endpoints, same booking confirmation (decided by the BE) — only the
transport is speech. All models run **locally**; the BE (separate LAN machine with the LLM and
SQLite) is reached over HTTP only.

Two modes share one conversation engine (`orchestrator.py`):

| Mode | Command | What it is | Use it for |
|---|---|---|---|
| **v1 live** | `python -m voicebot` | Real-time, full-duplex: browser/mic → WebSocket → VAD → STT → BE (SSE) → TTS → speaker, with barge-in | The demo with interruptions |
| **v2 on-demand** | `python -m voicebot.v2` | Press ENTER, speak, hear the answer. Same chat conversation, one question = one answer, no streaming, no echo problems | Any PC, noisy rooms, no browser; the safe fallback |
| **live from any PC** | `python -m voicebot.live_client ws://host:8003/ws/voice` | Live call with the local mic/speaker (browsers refuse the mic on plain-HTTP LAN addresses), auto-reconnect | Live mode from another machine |

v2 can also ride on the running CHAT service (`CHAT_SERVICE_URL=http://<chat>:8002`): then the
voice bot is just STT/TTS around `chat/api.py`, with the chat bot working invisibly underneath.

## Files

```
voice/
├── pyproject.toml           # packaging + pytest (pythonpath=src) + mypy strict + ruff
├── Dockerfile               # multi-stage image of the live server
├── test.bat                 # tests with the shared .venv, one line
├── src/voicebot/
│   ├── __main__.py          # `python -m voicebot`: uvicorn, graceful shutdown, JSON logs
│   ├── config.py            # Settings (env / shared .env), path resolution for models
│   ├── interfaces.py        # AbstractVAD / AbstractSTT / AbstractLLMOrchestrator / AbstractTTS
│   ├── vad.py               # EnergyVAD (default) + WebRtcVADWrapper, time-based, chunk-size independent
│   ├── stt.py               # FasterWhisperSTT (local, shared, warm) + scriptable FakeSTT
│   ├── tts.py               # PiperTTS (old+new piper API, sentence streaming) + FakeTTS
│   ├── orchestrator.py      # ★ the chat conversation: registration -> anonymise -> BE -> restore
│   ├── contacts.py          # registration dialogue (name + phone, spoken digits, it/en)
│   ├── anonymizer.py        # PII removal with restorable [TYPE_N] placeholders (+ stream restorer)
│   ├── pii.py               # stateless last-line PII net on everything leaving for the BE
│   ├── messages.py          # everything the bot says without the LLM (it/en)
│   ├── prompts.py           # the agent's role/actions prompt (English)
│   ├── backend.py           # BackendClient: retries, error mapping, SSE, /api/customers
│   ├── chat_service.py      # optional v2 transport through chat/api.py
│   ├── v2.py                # on-demand voice chat (mic -> STT -> chat -> TTS -> speaker)
│   ├── live_client.py       # headless live call with reconnection
│   ├── diagnostics.py       # shared checks behind /diag and the doctor
│   ├── doctor.py            # `python -m voicebot.doctor`: why does it not work?
│   ├── audio.py             # PCM helpers, SentenceChunker, speakable()
│   ├── logging_json.py      # structured JSON logging
│   └── pipeline/
│       ├── session.py       # ★ core loop: 3 asyncio tasks + bounded queues + barge-in
│       ├── server.py        # FastAPI: /health /ready /diag /ws/voice + test pages
│       └── *.html           # /prova-vocale (test page), /tech*, English
└── tests/                   # ~120 tests, no models and no network needed
```

## The conversation (identical to the chat bot)

1. **The bot speaks first** and asks for name + phone (same text as the chat, adapted for speech).
2. **Registration phase** — `contacts.py`: extract name/phone from one utterance (digits can be
   spoken: "tre tre tre uno due tre…"), read the number back digit by digit, wait for yes/no,
   accept corrections, give up after 3 empty turns. Then `POST /api/customers` → anonymous
   `customer_id`. **The LLM never takes part and never sees these data.**
3. **Chat phase** — every utterance: `anonymizer.anonymize()` → BE → `restore()` → TTS.
   Placeholders (`[NOME_1]`, `[TELEFONO_1]`) have the chat bot's exact format, which the BE recognises.
4. **No local intent shortcuts.** The BE agent decides everything: tool calls, the yes/no confirmation
   of bookings, allergy answers, the "not registered" rule.

## Core loop (producer–consumer)

```
WS reader ─PCM→ audio_in_q ─→ [VAD] ─utterance→ segment_q ─→ [STT] ─text→ text_q
   ─→ [LLM turn task] ─tokens→ token_q ─→ [TTS per sentence] ─PCM→ audio_out_q ─→ WS writer
```

- Every queue is bounded: backpressure, never unbounded memory. Live audio drops the oldest frame
  when late; speech output blocks instead (dropping would cut words).
- The turn runs as its own task, so **barge-in can cancel it at any moment**, even while the BE is
  still "thinking". Speech must last `BARGE_IN_MIN_MS` (default 300) to count: clicks and echo are ignored.
- While the client is still playing audio sent faster than real time the bot is considered speaking.
- STT and TTS are loaded once at startup (in the background: `/health` answers immediately,
  `/ready` flips when the models are warm) and shared by all calls.
- Shutdown: poison pills, task cancellation, bounded joins; JSON logs never contain what the caller said.

## BE contract used

| Method | Path | Use |
|---|---|---|
| GET | `/api/health` (`/health`) | readiness, LLM model |
| POST | `/api/customers` | `{name, phone(E.164), consent}` → `{customer_id}` — the only call carrying personal data |
| POST | `/api/chat` | v2: `{message, session_id, customer_id, client_type:"voice"}` → `{reply}` |
| POST | `/api/chat/stream` | v1: same body, SSE `data: {"token": ".."}` … `data: [DONE]` |

`POST /api/chat` is never retried after a read timeout (the LLM could book twice); GETs are retried
with backoff.

## WebSocket protocol `/ws/voice`

- client → server: binary PCM16LE mono 16 kHz frames (any size) · `{"cmd":"eos"}` · `{"cmd":"reset"}` (new conversation)
- server → client: binary PCM16 (TTS, at `tts_sample_rate` of the ready event) and JSON events:
  `ready` `loading` `heard` `transcript` `thinking` `reply` `barge_in` `error`
- Reconnection: a connection is stateless; clients reconnect with exponential backoff
  (the test page and `live_client` both do).

## Run it locally (no BE machine needed)

```bat
REM from the repo root, once
python setup\setup_env.py

REM terminal 1: a stub BE with the real contract (registration, confirmation flow)
.venv\Scripts\python voice\tests\stub_be.py 8001

REM terminal 2: the voice bot pointed at it (real models; add STT_BACKEND=fake TTS_BACKEND=fake to skip them)
set BACKEND_BASE_URL=http://127.0.0.1:8001
.venv\Scripts\python -m voicebot.doctor
.venv\Scripts\python -m voicebot            REM then open http://localhost:8003/prova-vocale
.venv\Scripts\python -m voicebot.v2 --text  REM or chat by keyboard, hear the replies
```

With the real three-machine setup only `BACKEND_BASE_URL=http://<BE-IP>:8000` changes.

## When something does not work

```bat
.venv\Scripts\python -m voicebot.doctor [--be-url http://10.10.0.5:8000] [--load-models] [--json]
```

prints OK/WARN/FAIL for the interpreter, `.env`, packages, Whisper/Piper files, audio devices,
the voice port, **BE reachability, LLM health and the registration endpoint**, each with the fix.
The same report is live at `http://<voice>:8003/diag` and in the STATUS drawer of the test page.

## Tests

```bat
cd voice
..\.venv\Scripts\python -m pytest tests -q     REM or test.bat
..\.venv\Scripts\python -m mypy src            REM strict typing
```

`tests/conftest.py` makes every test hermetic (ignores your `.env`, forces fake STT/TTS) and prints a
clear message when pytest runs with an interpreter that lacks the dependencies (VS Code often selects
the system Python instead of `.venv`). Layers: units (VAD, chunker, STT/TTS, config), contacts,
anonymiser, backend client (mock transport), orchestrator (stub BE over HTTP), pipeline (barge-in,
cancellation, failures), server + live client over real sockets (registration → booking, reconnection).

## Docker

```bat
docker build -t voicebot voice
docker run --rm -p 8003:8003 --env-file .env -v %cd%\voice\models:/app/models:ro voicebot
```

Multi-stage build (wheels built in the first stage, slim runtime, non-root user, healthcheck on `/health`).
Models are mounted, not baked in. Set `BACKEND_BASE_URL` to the BE machine's LAN address.

## Brief constraints — where they are met

1. Separate machines: VOICE is a standalone service, it talks to the BE only through `BACKEND_BASE_URL`.
2. Network: HTTP/SSE + WebSocket only; no import of BE/CHAT code (the optional chat-service transport is HTTP too).
3. Personal data: removed before sending (`anonymizer.py`, `pii.py`); name/phone go only to `/api/customers`.
4. Local models: faster-whisper, Piper, Ollama on the BE; no cloud provider anywhere in the code.
