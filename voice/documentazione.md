# Voice bot — Technical documentation (Traccia 3, VOICE member)

> Also served at `http://localhost:8003/tech` (printable to PDF). Aligned with the real BE
> (`backend/api/routes.py`) and with the chat bot (`chat/api.py`, `chat/contatti.py`, `chat/anonimizzatore.py`).

## 1. What it does and the brief's constraints

A voice bot to book, change and cancel a table, read the menu and give restaurant information.
**It behaves exactly like the chat bot** — same registration dialogue, same anonymisation, same BE
endpoints and confirmation protocol — with speech in and out.

| # | Constraint | How |
|---|---|---|
| 1 | Three different machines | VOICE is a standalone service; it reaches the BE only through `BACKEND_BASE_URL` |
| 2 | Communication over the network | HTTP/SSE + WebSocket only; **zero imports** of BE/CHAT code in `voice/` |
| 3 | Personal data removed before sending | `anonymizer.py` (same rules as the chat bot) + `pii.py` safety net; name/phone only to `POST /api/customers` |
| 4 | 100% local models | faster-whisper, Piper, VAD, Ollama (`gemma4:12b`) on the BE — no cloud provider in the code |

## 2. Network architecture

```
 mic/browser or live_client (VOICE machine or caller)
   │ WebSocket PCM16LE 16 kHz   ws://<VOICE-IP>:8003/ws/voice
   ▼
 VOICE :8003   VAD → STT → chat engine → TTS
   │ HTTP/SSE:  POST /api/customers · POST /api/chat · POST /api/chat/stream
   ▼
 BE :8000   LangGraph + Ollama gemma4:12b + SQLite  (separate LAN machine)
```

Why a shared Git repository if the components only talk over HTTP: the repo gives everyone the same
**contract** (real endpoints), the **stubs** for offline tests and one **setup** (`setup/` → one `.venv`).
At runtime each component uses only its own folder.

## 3. The conversation engine (`orchestrator.py`)

Port of `chat/api.py`, step by step:

1. **Registration phase.** The bot speaks first. `contacts.py` extracts name + phone from one
   utterance, reads the phone back digit by digit, waits for yes/no, accepts corrections, gives up
   after 3 turns without data (then continues as an anonymous customer: menu and info only).
   Spoken digits are normalised ("tre tre tre uno due tre…", "più 39…", "333, 123, 4567").
   `POST /api/customers` returns the anonymous `customer_id`. The LLM never sees any of this and the
   history keeps only "(registration data)".
2. **Chat phase.** `anonymize → BE → restore`. Placeholders keep the chat bot's `[TYPE_N]` format
   (`[NOME_1]`, `[TELEFONO_1]`…), which `backend/graph/workflow.py` recognises. The streaming restorer
   never speaks half a placeholder.
3. **No local shortcuts.** Earlier versions detected "menu"/"booking" with regexes, used a hard-coded
   date and read raw JSON aloud. All removed: the BE agent owns intent, tools, confirmation, allergy
   answers and the "not registered" rule.
4. **Errors become short apologies** (BE down / slow / LLM down / server error), never technical text.

`prompts.py` holds the agent's role and actions prompt (English). The BE builds its own voice prompt
from `client_type="voice"` and reads only the last user message; the prompt is therefore the
**specification** of the voice behaviour (the BE team's `backend/graph/prompts.py` should say the
same), is sent as the `system` message of each stream request, and `LLM_SYSTEM_PROMPT` overrides it.

## 4. Audio core loop (`pipeline/session.py`)

Producer–consumer over **bounded** `asyncio.Queue`s:

```
WS reader ─PCM→ audio_in_q ─→ VAD ─→ segment_q ─→ STT ─→ text_q ─→ LLM turn ─token_q→ TTS ─→ audio_out_q ─→ WS writer
```

- **Real streaming:** tokens feed the TTS as they arrive; synthesis per complete sentence
  (`SentenceChunker`), so audio starts before the LLM finishes. (The BE runs the whole inference before
  streaming, so the first token costs one turn; v2 avoids the question by being one-shot.)
- **Barge-in:** speech ≥ `BARGE_IN_MIN_MS` while the bot is speaking cancels the turn task (even while
  the BE is thinking), drops queued audio, tells the client. The VAD is *not* reset: it is already
  capturing the interrupting utterance. The bot counts as speaking until the client has played everything.
- **Time-based VAD:** pause detection uses real audio duration, independent of chunk size (browser: 128 ms,
  Python client: 20 ms).
- **Failures are contained:** a crashing STT/LLM turn emits an `error` event and the call continues.
- **Shutdown:** poison pills, cancellation, bounded joins; shared models are not closed per call.

## 4b. Final spoken report and the site

- **Report.** When a BE reply mentions a booking code (`RES-…`) and the caller is registered, the orchestrator
  fetches `GET /api/reservations/{code}?customer_id=` (the BE answers 404 for anybody else's code) and the
  voice bot reads back the real data — date, time, party size, room, table, code, status — then asks for a
  last yes (`is_plain_yes`: short and unqualified; "yes, but at 9" goes to the agent). Cancellation and
  modification are reported too; the same state is never read twice; a failed lookup means silence, never a
  wrong report. Numbers, dates and times are written as words (`spoken.py`) because the TTS reads "20:30" badly.
- **Site.** `http://<voice>:8003/` is the same kind of site as the chat bot's (look copied from `frontend/`):
  menu, hours, the voice assistant and **My reservations** (live status, lookup by code). Menu/info/lookups go
  through `/site/*` of the voice server; the lookup works only for the registered customer of that browser.
- **Events to the page:** `registered` (anonymous customer id) and `reservation` (code, date, time, guests,
  status, table, room) next to `transcript`, `reply`, `barge_in`…
- **Commands:** `voiceoice local` (stub BE, nothing else needed) · `python entrypointvvia.py` (real,
  three machines) · `voiceoice real|doctor|v2|live|test`; all also as `python -m voicebot <command>`.

## 5. Modes

- **v1 live** — `python -m voicebot`, page `/prova-vocale`, WebSocket `/ws/voice`.
- **v2 on-demand** — `python -m voicebot.v2 [--text] [--no-speaker]`: mic → STT → chat conversation
  (`POST /api/chat`) → TTS → speaker. Same engine, no streaming, no WebSocket, no barge-in, so none of the
  live-mode problems (echo, half-duplex audio, VAD tuning, browser mic restrictions). With
  `CHAT_SERVICE_URL` set it drives the running CHAT service instead (`POST /chat/session|message`).
- **live_client** — `python -m voicebot.live_client [url] [--half-duplex]`: live call with the local mic,
  no browser, automatic reconnection with exponential backoff.

## 6. Models and dependencies

| Use | Model | Where |
|---|---|---|
| Dialogue LLM | `gemma4:12b` via Ollama | BE machine |
| STT | faster-whisper `tiny` (configurable), language follows `VOICE_LANGUAGE` | VOICE machine, auto-downloaded on first use |
| TTS | Piper `it_IT-riccardo-x_low` (sample rate read from the model) | `voice/models/` (setup downloads it) |
| VAD | energy (default) / webrtc | VOICE machine |
| PII NER (optional) | spaCy `it_core_news_md` | extra safety net; regex layers work without it |

Per-role requirements: `setup/requirements/voice.txt` (+ base). `voice/pyproject.toml` mirrors them.

## 7. Configuration (`.env`, see `.env.example`)

`BACKEND_BASE_URL` · `VOICE_LANGUAGE` (`it`/`en`: spoken language) · `REQUIRE_REGISTRATION` (mirror of the
BE switch) · `CHAT_SERVICE_URL` (v2 via chat) · `STT_BACKEND`/`TTS_BACKEND` (`fake` for dry runs) ·
`VAD_*` · `BARGE_IN_MIN_MS` · `PIPER_MODEL_PATH` (resolved from cwd, repo root or `voice/`) ·
`PRELOAD_MODELS` · `LOG_LEVEL`. Real environment variables win over the `.env` file.

## 8. Tests — two modes

- **Offline** (`pytest tests`, 150+ tests, no models, no network): `tests/stub_be.py` is an HTTP stub of the
  real BE contract (registration validation, registration rule, yes/no confirmation, failures on demand);
  fake STT/TTS; the real client, orchestrator, pipeline, server and live client run over real sockets.
- **LAN**: replace the stub by the real BE changing only `BACKEND_BASE_URL`.

Run with the shared `.venv` (`voice\test.bat` or `..\.venv\Scripts\python -m pytest tests -q`).
`tests/conftest.py` ignores your `.env` and explains a wrong interpreter.

## 9. Cross-test checklist — what to ask the colleagues

**BE colleague (needs their machine):**
1. LAN IP and confirmation that the BE listens on `0.0.0.0:8000`.
2. `ollama serve` running, `ollama list` shows `gemma4:12b`.
3. Windows firewall: TCP 8000 inbound.
4. `GET /api/health` → `"status":"online"` and `POST /api/customers` answers 422 on an empty body.
5. Decide `REQUIRE_CUSTOMER_REGISTRATION` and mirror it in our `REQUIRE_REGISTRATION`.
6. Make the BE's voice prompt (`backend/graph/prompts.py`) match `voice/src/voicebot/prompts.py`.
7. Smoke test from this machine: `python -m voicebot.doctor --be-url http://<IP-BE>:8000`.

**CHAT colleague (consistency, not connection):**
8. Placeholder format is now identical (`[NOME_1]`…), keep it that way.
9. Optionally try v2 on top of their service: `CHAT_SERVICE_URL=http://<chat>:8002`.

**This machine:** firewall TCP 8003 inbound; `BACKEND_BASE_URL=http://<BE-IP>:8000`;
`python -m voicebot.doctor` is all green.

## 10. Strengths and weaknesses (honest, for the customer)

**Strengths:** identical behaviour to the chat bot · low perceived latency (TTS overlaps the stream) ·
natural interruption (barge-in) · resilient (retry/backoff, bounded queues, reconnection) · privacy by
design · 100% on-premise · diagnosable in seconds · testable without network or models.

**Weaknesses and risks:** slow first token (BE infers the whole answer before streaming) · STT `tiny`
trades accuracy for CPU (use `small`/`medium` with a GPU) · no speaker diarisation (one voice at a time) ·
no authentication on WS/BE (fine on a LAN demo, add tokens for production) · energy VAD degrades with
noise (use `VAD_MODE=webrtc`) · speaker echo without headphones/AEC interrupts the bot (browser AEC is on;
`live_client --half-duplex` avoids it) · Piper reads codes letter by letter via text tricks, not phonemes.

## 11. Demo start

```bat
python setup\setup_env.py
.venv\Scripts\python -m voicebot.doctor
.venv\Scripts\python -m voicebot            REM http://localhost:8003/prova-vocale  ·  /tech  ·  /diag
.venv\Scripts\python -m voicebot.v2         REM voice chat from any PC (local microphone)
```
