# Voice bot — table booking for the restaurant (Traccia 3, VOICE member)

The voice bot is the **chat bot with ears and a mouth**: same BE endpoints, same anonymisation, same registration
(name + phone) and the same booking confirmation (decided by the BE) — only the transport is speech. All speech models run
**locally**; the BE (separate LAN machine with the LLM and SQLite) is reached over HTTP only.

> Reference written from the code. Deeper technical notes: [documentazione.md](documentazione.md). Where every site lives:
> [../docs/SITI.md](../docs/SITI.md). The complete site (BE gateway): [../showcase/README.md](../showcase/README.md).

## Simple commands

| I want to… | Command (repo root) |
|---|---|
| **Test v1 locally** — stub BE, nothing else needed | `voice\voice local` (`--fake` = no speech models; `--port N`; `--no-browser`) |
| **Run the real component** on the VOICE PC (BE already up) | `voice\voice real` (checks the BE, waits for it up to `--wait` s, then serves) |
| **The full three-machine flow** | `python entrypoint\avvia.py` (pull, setup, firewall, waits for the BE, starts `python -m voicebot`, opens the sites) |
| Why does it not work? | `voice\voice doctor` (`--be-url URL`, `--json`, `--load-models`) |
| v2: voice chat from this PC, no browser | `voice\voice v2` (`--text` type instead of speak, `--no-speaker`, `--verbose`) |
| Live call from this PC, no browser | `voice\voice live ws://<voice-host>:8003/ws/voice` (`--half-duplex`) |
| Run the tests | `voice\voice test` |

`voice\voice` is `voice\voice.bat`; every command also works as `python -m voicebot <command>`
(`python -m voicebot` alone = `serve`, what `avvia.py` starts on the VOICE machine).

**What is v1?** The live voice bot (WebSocket, VAD, streaming, barge-in). `voice local` tests **v1**. v2 is the
one-question-one-answer speech chat (`voice v2`). Both share one conversation engine.

## Pages served by the voice server (port 8003)

| Page | What it is |
|---|---|
| `/` | the **restaurant site** with the voice assistant: orb button that morphs into the live orb (golden ring, animations), booking pop-up, chat window, **My reservations**, sections *Chi siamo · Menu · Le mie prenotazioni · Dove siamo · Contatti*, link to the staff area. Italian or English (`VOICE_LANGUAGE`) |
| `/test-voice` | the **test page**: liquid orb + side tabs **STATO** (voice / mic / WebSocket / BE / model, every check with its fix, latest events) and **TECNICA** (technical sheets), live transcript, booking pop-up, banner **VOICE / TESTS** with the BE it uses. `/prova-vocale` and `/prova-vocale-test` redirect here |
| `/tech` · `/tech-codice` · `/tech-idea` | printable technical sheet · how the code works · the idea in plain words |
| `/health` · `/ready` · `/diag` | liveness · models loaded **and** BE reachable (503 otherwise) · full JSON report of every check |
| `/site/config` · `/site/menu` · `/site/info` · `/site/reservation/{code}?customer_id=` | what the site calls: the voice server proxies the BE (the page never talks to the BE directly; the BE answers 404 for anybody else's code) |
| `/site/chat/session` · `/site/chat/message` | the site's chat window: forwarded to the CHAT service when `CHAT_SERVICE_URL` is set (else 503 "not connected") |
| `/ws/voice` | the call (WebSocket) |

CORS is open (`*`): the site can be served from another origin (the BE gateway does). LAN demo setting.

## The conversation (same rules as the chat bot)

`orchestrator.py` (`BackendOrchestrator`), two phases:

1. **CHAT** — the call opens with a short welcome ("Benvenuto alla Trattoria Bella Napoli! Come posso aiutarla?"); nothing is
   asked yet. Every utterance goes **anonymise → BE (`/api/chat` or the SSE stream) → restore placeholders → TTS**.
   Menu and information never need registration.
2. **REGISTRATION** — entered **only when the caller talks about booking** (`contacts.wants_booking`, e.g. "prenotare", "tavolo per"):
   ask name + phone in one utterance (digits may be spoken: "tre tre tre…"; a number cut by a pause is joined), read the phone back digit
   by digit, wait for yes/no, accept corrections, give up after 3 empty turns (then only menu/info). Then `POST /api/customers` →
   anonymous `customer_id`. **The LLM never takes part and never sees these data.** The request that triggered it is kept and sent to the BE
   (anonymised) right after the registration, so the caller does not repeat it. It stays stored until the BE has really answered: a barge-in or
   a BE error during that first slow turn cannot lose it (the caller would be registered with no booking).

Around the BE answer:

- **Anonymiser** (`anonymizer.py`): `[TYPE_N]` placeholders (`[NOME_1]`, `[TELEFONO_1]`…, the chat bot's format, recognised by the BE); a
  streaming restorer never speaks half a placeholder; `pii.scrub_pii` is a stateless last-line net on everything leaving for the BE.
- **Tool-talk guard** (`toolguard.py`): a reply in which the LLM names a tool ("devo prima chiamare get_menu…") is dropped and the turn retried
  once with an instruction; if it happens again a neutral sentence is spoken. Only the *shape* of the text is checked.
- **Spoken final report**: after a booking, change or cancellation (a `RES-…` code in the reply) the bot reads back the **real data** from
  `GET /api/reservations/{code}?customer_id=` (built by code, not by the LLM; numbers, dates, times as words via `spoken.py`) and asks for a last
  yes. A short unqualified yes ("sì", "sì, tutto corretto") closes it ("Perfetto…", event `reservation_confirmed`, fresh BE session); "sì, ma alle 21"
  goes to the agent as a change; a no asks what to change. The same state is never read twice; if the lookup fails the bot stays silent.
- **Context windows**: the BE keeps the dialogue as the LLM's context. After `CONTEXT_MAX_EXCHANGES` (20) BE turns without reaching a booking the
  bot starts a fresh BE session with a spoken recap; after `CONTEXT_MAX_RESETS` (3) refreshes it ends the call politely (event `call_ended`). The
  customer stays registered. A reached booking resets the counters.
- **BE warm-up** (`WARM_BACKEND`): at start-up one throw-away turn makes the LLM read its long prompt once, so the first caller does not wait.
- **Errors** become short spoken apologies (BE unreachable / slow / LLM down / server error), never technical text.

There are **no local intent shortcuts**: the BE agent decides tools, confirmation, allergy answers and the "not registered" rule.
`prompts.py` holds the agent's role/actions prompt in Italian; the BE reads only the last user message and builds its own voice prompt from
`client_type="voice"`, so the text is the specification of the behaviour (and is sent as `system` message of each stream request).
`LLM_SYSTEM_PROMPT` overrides it.

## Core loop (producer–consumer, `pipeline/session.py`)

```
WS reader ─PCM→ audio_in_q ─→ [VAD] ─utterance→ segment_q ─→ [STT] ─text→ text_q
   ─→ [LLM turn task] ─tokens→ token_q ─→ [TTS per sentence] ─PCM→ audio_out_q ─→ WS writer
```

- Every queue is bounded (backpressure). Live audio drops the oldest frame when late; speech output blocks (dropping would cut words).
- The turn is its own task, so **barge-in cancels it at any moment**, even while the BE is thinking. Speech must last `BARGE_IN_MIN_MS`
  (700 ms) to count (clicks and echo are ignored); while the client still plays audio sent faster than real time the bot counts as speaking. The VAD
  is not reset: it is already capturing the interrupting utterance.
- VAD timing uses the real duration of the audio (browser chunks are 128 ms, the Python client 20 ms): pause detection lasts the same for both.
- STT and TTS are loaded **once** at start-up in the background and shared by all calls (`/health` answers at once, `/ready` flips when warm).
- A crashing STT/LLM turn emits an `error` event and the call goes on. Shutdown: poison pills, cancellation, bounded joins; logs (JSON) never contain what the caller said.

## WebSocket protocol `/ws/voice`

- client → server: binary PCM16LE mono 16 kHz frames (any size) · `{"cmd":"eos"}` · `{"cmd":"reset"}` (new conversation)
- server → client: binary PCM16 (TTS, at `tts_sample_rate` of the `ready` event) and JSON events:

| Event | Meaning |
|---|---|
| `loading` / `ready` | models loading / call open (`session_id`, `sample_rate`, `tts_sample_rate`) |
| `heard` · `transcript` · `thinking` · `reply` | pause captured · what STT understood · LLM working · full text of the answer |
| `barge_in` | the caller interrupted: stop playing |
| `registered` | registration done (anonymous `customer_id`) |
| `reservation` | booking created / changed / cancelled: `code`, `status`, `date`, `time`, `guests`, `table`, `location`, `customer_id`, and for the caller's own page `name`, `area` (the room only if they asked for one) |
| `reservation_confirmed` | the caller said the final yes (the page closes its pop-up) |
| `call_ended` | the conversation ended the call after the last sentence |
| `error` | `detail`: `stt_timeout`, `stt_failed`, `turn_failed`, `models_failed` |

A connection is stateless: clients reconnect with exponential backoff (the pages and `live_client` do).

## BE contract used

| Method | Path | Use |
|---|---|---|
| GET | `/api/health` (`/health`) | readiness, LLM model |
| POST | `/api/customers` | `{name, phone(E.164), consent}` → `{customer_id}` — the only call carrying personal data |
| POST | `/api/chat` | v2 and warm-up: `{message, session_id, customer_id, client_type:"voice"}` → `{reply}` |
| POST | `/api/chat/stream` | v1: same body, SSE `data: {"token": ".."}` … `data: [DONE]` |
| GET | `/api/reservations/{code}?customer_id=` | final report and "My reservations" (owner only, 404 otherwise) |
| GET | `/api/menu` · `/api/info` | the site's menu and info (through `/site/*`) |

`POST /api/chat` is never retried after a read timeout (the LLM could book twice); GETs retry with backoff.

## Configuration (`.env` at the repo root, see `.env.example`; real environment variables win)

| Variable | Default | Meaning |
|---|---|---|
| `BACKEND_BASE_URL` | `http://localhost:8000` | the BE (LAN IP of its machine, not `localhost`, on the real setup) |
| `VOICE_HOST` · `VOICE_PORT` | `0.0.0.0` · `8003` | where the voice server listens |
| `VOICE_LANGUAGE` | `it` | spoken language of the bot's own sentences and of STT (`it`/`en`) |
| `REQUIRE_REGISTRATION` | `true` | mirror of the BE switch: name + phone before booking |
| `CHAT_SERVICE_URL` | empty | CHAT service for the site's chat window and v2 (the gateway does not use it) |
| `CONTEXT_MAX_EXCHANGES` · `CONTEXT_MAX_RESETS` | `20` · `3` | context windows (see above) |
| `WARM_BACKEND` · `PRELOAD_MODELS` | `true` | warm the BE / load STT+TTS at start-up |
| `STT_BACKEND` · `STT_MODEL` | `faster-whisper` · `small` | `fake` = no recognition; `tiny` mangles digits and names |
| `STT_LANGUAGE` · `STT_TIMEOUT_S` · `STT_INITIAL_PROMPT` | follow `VOICE_LANGUAGE` · 30 · empty | the prompt is off: it can be echoed back |
| `TTS_BACKEND` · `PIPER_MODEL_PATH` | `piper` · `voice/models/it_IT-riccardo-x_low.onnx` | `fake` = beeps; the path resolves from cwd, repo root or `voice/` |
| `VAD_MODE` · `VAD_*` | `energy` · threshold 900, silence 600 ms, min speech 450 ms | noise rejection: below the threshold is not voice, an utterance shorter than the minimum never reaches the STT. `webrtc` optional |
| `BARGE_IN_ENABLED` · `BARGE_IN_MIN_MS` | `true` · `700` | interruptions: speech must last this long while the bot talks (bangs and coughs are shorter) |
| `BACKEND_TIMEOUT_S` · `BACKEND_CHAT_TIMEOUT_S` | `15` · `120` | the local LLM can be slow |
| `WS_IDLE_TIMEOUT_S` · `LOG_LEVEL` | `60` · `INFO` | |

## Files

```
voice/
├── pyproject.toml           packaging + pytest (pythonpath=src) + mypy strict + ruff
├── voice.bat · test.bat     one entry point (local|real|doctor|v2|live|test) · tests with the shared .venv
├── Dockerfile · .dockerignore   multi-stage image of the live server (not built in CI here)
└── src/voicebot/
    ├── __main__.py          `python -m voicebot [serve|real|local|doctor|v2|live]`
    ├── local.py             `local`: stub BE + voice server + test page in one process
    ├── config.py            Settings, .env lookup, model path resolution
    ├── interfaces.py        AbstractVAD / AbstractSTT / AbstractLLMOrchestrator / AbstractTTS
    ├── vad.py · stt.py · tts.py · audio.py   energy/webrtc VAD · faster-whisper · Piper (old and new API) · PCM helpers, SentenceChunker, speakable()
    ├── orchestrator.py      ★ the conversation: welcome, lazy registration, anonymise, BE, restore, report, context windows
    ├── contacts.py · anonymizer.py · pii.py · toolguard.py   registration dialogue · placeholders · last-line PII net · tool-talk guard
    ├── messages.py · prompts.py · spoken.py   spoken sentences it/en · agent prompt (Italian) · numbers/dates/times as words
    ├── backend.py · chat_service.py · peers_file.py   BE client · CHAT-service transport (v2) · lazy CHAT address from the peers file
    ├── v2.py · live_client.py   on-demand voice chat · live call without a browser (auto-reconnect)
    ├── diagnostics.py · doctor.py   the checks behind /diag and `doctor`
    ├── logging_json.py      structured JSON logging
    ├── devtools/stub_be.py  stub BE with the real contract (registration, confirmation, cancel/modify, lookup, menu, info)
    └── pipeline/
        ├── session.py       ★ core loop: 3 asyncio tasks + bounded queues + barge-in
        ├── server.py        FastAPI: pages, /site/*, /health /ready /diag, /ws/voice, BE warm-up
        ├── site/            the restaurant site (index.html, app.js, site.css)
        └── voice_test.html · tech*.html   test page · technical sheets
```

## The complete site and the BE gateway

On the real setup CHAT and VOICE never talk to each other: the **complete site** (chat + voice + staff area + database) is served by
the **gateway on the BE** (`https://<IP-BE>:8090`, reverse proxy to BE, VOICE and CHAT; `showcase/`). The same site page is served here at `/` for
local use. `python entrypoint\avvia.py` opens each machine's test page and the complete site. Details, certificate and discovery:
[../showcase/README.md](../showcase/README.md).

## When something does not work

`voice\voice doctor` prints OK/WARN/FAIL for the interpreter, `.env`, packages, Whisper/Piper files, audio devices, the voice port, **BE
reachability, LLM health and the registration endpoint**, each with its fix. The same report is live at `/diag` and in the STATO tab.

## Tests

```bat
cd voice
..\.venv\Scripts\python -m pytest tests -q      :: 225+ tests, no models and no network needed (or: voice\voice test)
..\.venv\Scripts\python -m mypy src             :: strict typing
```

`tests/conftest.py` makes every test hermetic (ignores your `.env`, fake STT/TTS) and explains a wrong interpreter (VS Code often picks the system
Python instead of `.venv`). Layers: units, contacts, anonymiser, tool guard, backend client (mock transport), orchestrator and context windows
(stub BE over HTTP), pipeline (barge-in, cancellation, failures), server + live client over real sockets, site, report, doctor, and the
`showcase/` gateway (proxying incl. WebSocket, TLS, discovery, firewall port).

## Docker

```bat
docker build -t voicebot voice
docker run --rm -p 8003:8003 --env-file .env -v %cd%\voice\models:/app/models:ro voicebot
```

Multi-stage (wheels in the first stage, slim runtime, non-root user, healthcheck on `/health`). Models are mounted, not baked in.
Set `BACKEND_BASE_URL` to the BE machine's LAN address. Optional `--build-arg WITH_NER=1` adds the spaCy name recogniser.
The image has never been built here (no Docker on the development PCs).

## Brief constraints — where they are met

1. Separate machines: VOICE is a standalone service, it reaches the BE only through `BACKEND_BASE_URL`.
2. Network only: HTTP/SSE + WebSocket; no import of BE/CHAT code. CHAT and VOICE meet only through the BE gateway.
3. Personal data: removed before sending (`anonymizer.py`, `pii.py`); name and phone go only to `/api/customers`; logs never contain speech.
4. Local models: faster-whisper, Piper, Ollama on the BE; no cloud provider anywhere in the code.
