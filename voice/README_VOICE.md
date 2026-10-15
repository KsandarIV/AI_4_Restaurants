# Voice bot — table booking for the restaurant (Traccia 3, VOICE member)

The voice bot is the **chat bot with ears and a mouth**: same registration dialogue, same
anonymisation, same BE endpoints, same booking confirmation (decided by the BE) — only the
transport is speech. All models run **locally**; the BE (separate LAN machine with the LLM and
SQLite) is reached over HTTP only.

## Simple commands

**What is v1?** The live voice bot (WebSocket, VAD, streaming, barge-in). `voice local` tests **v1**, not the
speech-to-text/text-to-speech chat (that is `voice v2`). You test v1 on the **test page** (the orb, with the
side tabs TECNICA and STATO):

| I want to… | Command (from the repo root) | Opens |
|---|---|---|
| **Test v1 locally** — stub BE, nothing else needed | `voice\voice local`  (`--fake` = no speech models, page/flow only) | `/test-voice`: banner **VOICE / TESTS — BE in uso: stub** |
| **Test v1 against the real BE on the LAN** (one component) | `voice\voice real`  then open `http://localhost:8003/test-voice` | `/test-voice`: banner shows the real BE in use |
| **The full three-machine flow**, as always | `python entrypoint\avvia.py`  (pull, setup, firewall, waits for the BE, starts `python -m voicebot`) | same pages on the VOICE machine |
| Find out why something does not work | `voice\voice doctor`  (also the STATO tab) | |
| v2: voice chat from this PC, no browser, one question = one answer | `voice\voice v2`  (`--text` = type instead of speak) | |
| Live call from this PC without browser | `voice\voice live ws://<voice-host>:8003/ws/voice` | |
| Run the tests | `voice\voice test` | |

`voice\voice` is `voice\voice.bat`; the same commands work as `python -m voicebot <command>`.
Both pages are served by the same server and talk to the same BE (`BACKEND_BASE_URL`): the restaurant site at `/`
and the test page at `/test-voice` (technical tabs, live transcript, events, always with the banner that names the BE
in use). The old addresses `/prova-vocale` and `/prova-vocale-test` redirect to `/test-voice`.

The test page is the original one — liquid orb with its animations, **TECNICA** tab (technical sheets) and
**STATO** tab (voice / microphone / WebSocket / BE / model + every check with its fix + latest events) —
now also showing the live transcript under the orb, reconnecting by itself and stopping the sound at once
when you interrupt.

## The site (same kind of site as the chat bot's)

Open `http://localhost:8003/` (local mode prints the exact address). It has the restaurant look of
`frontend/` (copied stylesheet): menu with filters, hours/address/phone from the BE, the voice
assistant and **My reservations**. Bottom right there are two buttons: **Scrivi** (the chat bot) and **Prenota a voce**;
the voice button **morphs** (gradually) into a big floating orb hooked to the lower edge of the red band, with the golden ring growing from behind it and the dots born inside it; tapping the orb hangs up and it shrinks back into the button (no panel, no transcript: that is on
`/test-voice`). The chat window goes through `/site/chat/*` to the CHAT service and answers "non è collegato" unless
`CHAT_SERVICE_URL` is set.

- every booking made, changed or cancelled by voice appears there with its **live status**
  (`Confirmed` / `Cancelled`) read from the BE;
- "Check" looks up any code of yours; "Refresh all" re-reads them. Lookups only work from the browser
  where you registered (the anonymous `customer_id` is kept in `localStorage`) and the BE answers
  404 for anybody else's code;
- the page never talks to the BE directly: `/site/menu`, `/site/info`, `/site/reservation/{code}` go
  through the voice server. Page language follows `VOICE_LANGUAGE` (it/en).

The orb is the same liquid orb as the test page. Other pages: `/test-voice` (+ `/tech`, `/tech-codice`, `/tech-idea`, `/diag`).

## The spoken final report

After a booking, a change or a cancellation the voice bot **reads back what really happened** and asks
for a last yes — built by code from `GET /api/reservations/{code}` (owner only), not by the LLM:

> "Riepilogo finale per Mario Rossi: la sua prenotazione è confermata, per due persone, venerdì sedici
> ottobre, alle venti e trenta, in terrazza, tavolo undici. Il codice è R E S, 9 A 8 B 2 C. È tutto corretto?"

- **yes** (short, unqualified: "sì", "sì, tutto corretto") → "Perfetto per Mario Rossi, grazie! La aspettiamo…";
  "sì, ma alle 21" is NOT a yes: it goes to the agent as a change request;
- **no** → "Mi dica cosa vuole cambiare…" and the caller changes or cancels by voice;
- a change says "Prenotazione aggiornata…", a cancellation "La prenotazione RES-… risulta cancellata";
- the same state is never read twice; if the lookup fails the bot stays silent rather than say something wrong.

The same facts reach the page as `registered` / `reservation` events (that is what fills "My reservations").

## Modes

Two modes share one conversation engine (`orchestrator.py`):

| Mode | What it is | Use it for |
|---|---|---|
| **v1 live** | Real-time, full-duplex: browser/mic → WebSocket → VAD → STT → BE (SSE) → TTS → speaker, with barge-in | The demo with interruptions |
| **v2 on-demand** | Press ENTER, speak, hear the answer. Same chat conversation, one question = one answer, no streaming, no echo problems | Any PC, noisy rooms, no browser; the safe fallback |
| **live from any PC** | Live call with the local mic/speaker (browsers refuse the mic on plain-HTTP LAN addresses), auto-reconnect | Live mode from another machine |

v2 can also ride on the running CHAT service (`CHAT_SERVICE_URL=http://<chat>:8002`): then the
voice bot is just STT/TTS around `chat/api.py`, with the chat bot working invisibly underneath.

## Files

```
voice/
├── pyproject.toml           # packaging + pytest (pythonpath=src) + mypy strict + ruff
├── Dockerfile               # multi-stage image of the live server
├── voice.bat                # one entry point: local | real | doctor | v2 | live | test
├── test.bat                 # tests with the shared .venv, one line
├── src/voicebot/
│   ├── __main__.py          # `python -m voicebot [local|real|doctor|v2|live]`, graceful shutdown, JSON logs
│   ├── local.py             # `voicebot local`: stub BE + voice server + browser in one process
│   ├── spoken.py            # numbers/dates/times as words for the final report
│   ├── devtools/stub_be.py  # stub BE with the real contract (also used by tests/stub_be.py)
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
│   ├── prompts.py           # the agent's role/actions prompt (Italian, answers in the customer's language)
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
│       ├── site/            # the site: index.html, app.js, site.css (look copied from frontend/)
│       └── *.html           # /test-voice (diagnostic page), /tech*
└── tests/                   # 150+ tests, no models and no network needed
```

## The conversation

1. **Short welcome**: "Benvenuto alla Trattoria Bella Napoli! Come posso aiutarla?" Nothing is asked yet;
   menu and information work for anybody.
2. **Registration only when the caller talks about booking** (`wants_booking` in `contacts.py`: "prenotare",
   "tavolo", "book"...). The bot asks "name and a phone number" (no examples; a surname is accepted if given,
   never required): extract name/phone from one utterance (digits can be spoken), read the number back digit by
   digit, wait for yes/no, accept corrections, give up after 3 empty turns (it asks again at the next booking
   request). Then `POST /api/customers` → anonymous `customer_id`. **The LLM never takes part and never sees
   these data**; the request that started it is kept and sent to the BE (anonymised) right after, so the caller
   does not repeat it.
3. **Chat phase** — every utterance: `anonymizer.anonymize()` → BE → `restore()` → TTS.
   Placeholders (`[NOME_1]`, `[TELEFONO_1]`) have the chat bot's exact format, which the BE recognises.
4. **No local intent shortcuts** beyond "when to ask for contact data". The BE agent decides everything: tool
   calls, the yes/no confirmation of bookings, allergy answers.
5. **Booking pop-up on the site**: each booking/change shows a small summary (name, date, time, guests, room only
   if the caller asked for one). It closes **4 seconds after the caller's spoken final "yes"**
   (`reservation_confirmed` event) and never by click; a cancellation or hanging up closes it at once.
   The live transcript under the orb is shown only in local test mode.

**Agent prompt** (`prompts.py`): Italian, answers in the customer's language when it knows it (Italian by default),
asks about a room before confirming, refuses past dates. The BE only reads the last user message, so it is the
specification for the BE team until `backend/graph/prompts.py` adopts it. Speech recognition stays tied to
`STT_LANGUAGE` / `VOICE_LANGUAGE`: other languages are understood by the LLM only if Whisper transcribes them.

## Weak PC (laptop CPU, no GPU): context, speed, warm-up

Measured on an i5-1235U (12 threads), `gemma4` 8B Q4: the LLM reads its prompt at ~36 tokens/s and writes ~7 tokens/s.
The first BE turn after start-up costs ~70 s (it reads the long system prompt + tools once); once that prefix is cached
the next turns take ~3 s. So:

- **Lighter model, same weights** (nothing is downloaded): `ollama create gemma4-voice -f voice/local_llm/Modelfile`
  (context 8192 instead of 64k, 6 threads so Whisper keeps some cores), then `OLLAMA_MODEL=gemma4-voice` in the `.env` of
  the machine that runs the BE (and `OLLAMA_TIMEOUT_S=300` for the very first turn).
- **Warm-up** (`WARM_BACKEND=true`): at start-up the voice server sends one throw-away turn to the BE
  (session `voice_warmup`, customer `anon_warmup`), so the first caller does not pay the ~70 s.
- **Shared anonymous id**: the BE writes the customer id and the date at the top of the LLM's prompt, so every new id
  re-reads the whole prompt. All unregistered callers therefore use `anon_voice` (it identifies nobody and cannot book), and
  the warm-up pays the prompt once. A caller's first turn after registration (their own id) is still slow on a weak CPU.
- **Context management** (the BE keeps the dialogue as the LLM's context): every `CONTEXT_MAX_EXCHANGES` (20) BE turns
  without reaching a booking the bot starts a **fresh BE session** and says "sto gestendo molte richieste…, ripartiamo da
  capo: una prenotazione o una modifica?" (the customer stays registered: nobody repeats name or phone). The 3rd refresh adds
  "a breve potrei dover ricominciare tutto da capo"; the **4th** ends the call (`call_ended` event: the page waits for the last
  sentence, then hangs up) until the caller taps the orb again. Reaching a booking resets the counters, and the caller's final
  "yes" starts a fresh session, so the next request begins with an empty context. `CONTEXT_MAX_RESETS` (3) is the number of
  refreshes before the end.

**Tool talk filter** (`toolguard.py`): a small model sometimes answers "devo prima chiamare get_menu, vuole che verifichi?" instead of
using the tool. The first sentence of every BE reply is held back until it is judged (tool names, "I must call...", "vuole che
verifichi..."); if it leaks, the reply is dropped, the turn is retried once with an instruction to use the tools silently, and if it
leaks again the caller hears "non sono riuscito a recuperare questa informazione, può ripetere?". The prompt says the same.

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
| GET | `/api/reservations/{code}?customer_id=` | the final spoken report and the site's "My reservations" (owner only, 404 otherwise) |
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

## Run it locally by hand (what `voice local` does)

```bat
REM from the repo root, once
python setup\setup_env.py

REM terminal 1: a stub BE with the real contract (registration, confirmation flow)
.venv\Scripts\python voice\tests\stub_be.py 8001

REM terminal 2: the voice bot pointed at it (real models; add STT_BACKEND=fake TTS_BACKEND=fake to skip them)
set BACKEND_BASE_URL=http://127.0.0.1:8001
.venv\Scripts\python -m voicebot.doctor
.venv\Scripts\python -m voicebot            REM then open http://localhost:8003/test-voice
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
