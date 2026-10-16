# Voice bot — Technical documentation (Traccia 3, VOICE member)

> Architecture, design decisions and test/demo checklist, written from the code. Everyday reference (commands, pages, events,
> configuration, files): [README_VOICE.md](README_VOICE.md). Also served at `http://localhost:8003/tech` (printable to PDF).
> Aligned with the real BE (`backend/api/routes.py`, `backend/graph/workflow.py`) and the chat bot (`chat/api.py`, `chat/contatti.py`, `chat/anonimizzatore.py`).

## 1. What it does and the brief's constraints

A voice bot to book, change and cancel a table, read the menu and give restaurant information. **It behaves like the chat bot** — same BE
endpoints, same anonymisation, same registration, same confirmation protocol — with speech in and out.

| # | Constraint | How |
|---|---|---|
| 1 | Three different machines | VOICE is a standalone service; it reaches the BE only through `BACKEND_BASE_URL` |
| 2 | Communication over the network | HTTP/SSE + WebSocket only; **zero imports** of BE/CHAT code in `voice/`. CHAT and VOICE never talk to each other: they meet only through the gateway on the BE |
| 3 | Personal data removed before sending | `anonymizer.py` (same rules as the chat bot) + `pii.py` safety net; name and phone only to `POST /api/customers`; logs never contain what the caller said |
| 4 | 100% local models | faster-whisper, Piper, VAD, Ollama (`gemma4:12b`) on the BE — no cloud provider in the code |

## 2. Network architecture (a star with the BE in the middle)

```
 caller's browser or live_client (any PC)
        │ WebSocket PCM16LE 16 kHz   (/ws/voice, directly on the VOICE PC for the test page,
        │                             or /voice/ws/voice through the BE gateway for the complete site)
        ▼
 VOICE :8003   VAD → STT → conversation engine → TTS          ──HTTP/SSE──▶  BE :8000
                                                                  POST /api/customers · /api/chat · /api/chat/stream
                                                                  GET  /api/reservations/{code} · /api/menu · /api/info
 BE gateway :8090 (https)  serves the complete site and reverse-proxies:  /api,/docs → BE · /voice/* + WebSocket → VOICE · /voice/site/chat/* → CHAT
```

The complete site is **not** served by the voice PC: the gateway on the BE is the single origin (see [../showcase/README.md](../showcase/README.md):
discovery of the other PCs, self-announcement, TLS, why `*.localhost`). The voice server still serves the same site page at `/` and the test page at
`/test-voice`, and answers CORS so that page can be served from elsewhere.

Why a shared Git repository if the components only talk over HTTP: it gives everyone the same **contract** (the real endpoints), the **stubs** for offline
tests and one **setup** (`setup/` → one `.venv`). At runtime each component uses only its own folder.

## 3. The conversation engine (`orchestrator.py`)

Port of `chat/api.py`, with the phases in the order a real call needs:

1. **Welcome, nothing asked.** Menu and information never need registration; the call opens with one friendly sentence.
2. **Lazy registration.** When the caller talks about booking (`contacts.wants_booking`) the engine keeps the request, asks name + phone, reads the number back
   digit by digit, waits for yes/no, registers (`POST /api/customers`) and **replays the stored request to the BE**, so the BE's next sentence is the
   one that asks date, time and party size. The stored request survives a cancelled or failed turn (`_replay`, cleared only when the BE answered).
3. **Chat.** `anonymise → BE → restore`. Placeholders keep the chat bot's `[TYPE_N]` format, which `backend/graph/workflow.py` recognises. The streaming
   restorer never speaks half a placeholder.
4. **No local shortcuts.** The BE agent owns intent, tools, the yes/no confirmation (`workflow.py` proposes, code executes), allergy answers and the
   "not registered" rule. The voice side only guards the *shape* of the reply (`toolguard.py`: a reply that talks about tools is retried once).
5. **Spoken final report** from the BE's own data (`GET /api/reservations/{code}?customer_id=`), formatted by `spoken.py`, closed by a short unqualified yes.
6. **Context windows.** The BE keeps the whole dialogue as the LLM's context, so a call that goes round in circles is refreshed (spoken recap, same registered
   customer) after `CONTEXT_MAX_EXCHANGES` turns and ended politely after `CONTEXT_MAX_RESETS` refreshes (`call_ended`).
7. **Errors become short apologies**, never technical text; `BackendError` carries `kind` (unreachable/timeout/http/format) and the HTTP status.

`prompts.py` is the agent's role/actions prompt (Italian). The BE builds its own voice prompt from `client_type="voice"` and reads only the last user message,
so the prompt is the specification the BE team should mirror; `LLM_SYSTEM_PROMPT` overrides it.

## 4. Audio core loop (`pipeline/session.py`) — decisions that matter

Producer–consumer over **bounded** `asyncio.Queue`s (full description in the README). Why it is built this way:

- **The LLM turn is its own task.** A barge-in must be able to cancel it while the BE is still thinking (a slow first token is normal); a generation counter
  invalidates anything produced for a cancelled turn.
- **"Speaking" includes the client's playback.** Audio is sent faster than real time; the server computes when the client finishes playing and treats the bot as
  speaking until then, otherwise an interruption in the last seconds of a long answer would go unnoticed.
- **Interruptions must last `BARGE_IN_MIN_MS`.** Clicks, coughs and speaker echo are shorter; the VAD is not reset, because it is already recording the words
  that interrupted.
- **VAD timing is measured in audio time**, not frame counts: the browser sends 2048-sample (128 ms) chunks, the Python client 20 ms ones.
- **STT/TTS are shared and loaded once** in the background; `/ready` flips when they are warm. Loading per call would add seconds and gigabytes. Piper runs
  behind a lock (the phonemiser is not thread-safe) and supports both the old and the new `piper-tts` API.
- **TTS speaks sentence by sentence as tokens arrive** (`SentenceChunker`, `speakable()` removes markdown/emoji and spells booking codes), so audio starts before
  the LLM finishes. The BE itself runs the whole inference before streaming, so the first token still costs one turn; v2 hides that by being one-shot.
- **Live audio is lossy on purpose** (oldest frame dropped when late); speech output is not (it blocks).

## 5. Modes

- **v1 live** — `python -m voicebot`, pages `/` and `/test-voice`, WebSocket `/ws/voice`.
- **v2 on-demand** — `python -m voicebot.v2 [--text] [--no-speaker]`: mic → STT → the same conversation (`POST /api/chat`) → TTS → speaker. No streaming, no
  WebSocket, no barge-in, so none of the live-mode problems (echo, half-duplex audio, VAD tuning, browser mic restrictions). With `CHAT_SERVICE_URL` set it
  drives the running CHAT service (`/chat/session|message`) instead.
- **live_client** — `python -m voicebot.live_client [url] [--half-duplex]`: live call with the local mic, no browser, automatic reconnection with backoff.
  Without headphones the speaker interrupts the bot: use headphones or `--half-duplex`.

## 6. Models and dependencies

| Use | Model | Where |
|---|---|---|
| Dialogue LLM | `gemma4:12b` via Ollama | BE machine (not ours) |
| STT | faster-whisper `small` (language follows `VOICE_LANGUAGE`) | VOICE machine, downloaded on first start (**internet once**) |
| TTS | Piper `it_IT-riccardo-x_low` (the real sample rate is read from the model: 16 kHz) | `voice/models/` (setup downloads it) |
| VAD | energy (default) / webrtc | VOICE machine |
| PII NER (optional) | spaCy `it_core_news_md` | extra safety net; the regex layers work without it |

Measured on the development PCs: Whisper `tiny` hears "tre tre tre" as "33" and mangles names; `small` is accurate at ~1.5 s per 4 s of speech on CPU. The first
BE turn after a cold start can take over a minute (the LLM reads its prompt): `WARM_BACKEND` does it at start-up. Per-role requirements:
`setup/requirements/voice.txt` (+ base); `voice/pyproject.toml` mirrors them.

## 7. Configuration

All settings, defaults and meaning: [README_VOICE.md](README_VOICE.md#configuration-env-at-the-repo-root-see-envexample-real-environment-variables-win) and
`.env.example` (VOICE section). Real environment variables win over the `.env` file.

## 8. Tests — two modes

- **Offline** (`pytest tests`, 225+ tests, no models, no network): `devtools/stub_be.py` (also at `tests/stub_be.py`) is an HTTP stub of the real BE contract
  (registration validation, registration rule, yes/no confirmation, cancel/modify, owner-only lookup, failures on demand); fake STT/TTS; the real client,
  orchestrator, pipeline, server, live client and the `showcase/` gateway run over real sockets (WebSocket both ways, TLS, discovery).
- **Against a real BE**: change only `BACKEND_BASE_URL` (a private BE with a temporary database was used to verify the full booking path: request → name/phone →
  date/time/people → confirm → `RES-…` `CONFIRMED` in the DB and in the staff list).

Run with the shared `.venv` (`voice\voice test`). `tests/conftest.py` ignores your `.env` and explains a wrong interpreter. One test
(`test_old_be_without_registration_is_detected`) has failed under load in full runs and passes alone; it does not affect behaviour.

## 9. Cross-test checklist — what to ask the colleagues

**BE colleague (needs their machine):**
1. LAN IP and confirmation that the BE listens on `0.0.0.0:8000`.
2. `ollama serve` running, `ollama list` shows `gemma4:12b`; ask one question before the demo so the model is warm.
3. Windows firewall: TCP 8000 and **8090** inbound (`avvia.py` applies the rules; otherwise it prints the `netsh` commands). 8090 is the gateway the other PCs open.
4. `GET /api/health` → `"status":"online"` and `POST /api/customers` answers 422 on an empty body.
5. Decide `REQUIRE_CUSTOMER_REGISTRATION` and mirror it in `REQUIRE_REGISTRATION`.
6. Make the BE's voice prompt (`backend/graph/prompts.py`) match `voice/src/voicebot/prompts.py`.
7. Smoke test from this machine: `python -m voicebot.doctor --be-url http://<IP-BE>:8000`.

**CHAT colleague (consistency, not connection):**
8. Placeholder format is identical (`[NOME_1]`…): keep it that way.
9. The complete site reaches the chat through the BE gateway; the CHAT PC only has to be up (`:8002`) and announce itself (`avvia.py` does).

**This machine:** firewall TCP 8003 inbound; `BACKEND_BASE_URL=http://<BE-IP>:8000`; `python -m voicebot.doctor` is all green; Whisper `small` already downloaded.

## 10. Strengths and weaknesses (honest, for the customer)

**Strengths:** same behaviour as the chat bot · low perceived latency (TTS overlaps the stream) · natural interruption (barge-in) · resilient (retry/backoff that
never replays a booking, bounded queues, reconnection) · privacy by design · 100% on-premise · diagnosable in seconds (`doctor`, `/diag`, STATO tab) · testable
without network or models · the booking read-back comes from the database, not from the LLM.

**Weaknesses and risks:** slow first token (the BE infers the whole answer before streaming; cold LLM up to a minute) · STT `small` is accurate but costs ~1.5 s per
sentence on CPU · no speaker diarisation · no authentication on WS/BE and CORS `*` (fine on an isolated LAN demo; production needs TLS everywhere, an explicit origin
and a token between services) · self-signed certificate on the gateway (one click per browser) · energy VAD degrades with noise (`VAD_MODE=webrtc`) · speaker echo without
headphones/AEC interrupts the bot (browser AEC is on; `live_client --half-duplex` avoids it) · small local LLMs can still misbehave: the guard retries tool-talk once.

## 11. Demo start

```bat
python entrypoint\avvia.py                :: each PC, BE first; opens the test pages and the complete site
voice\voice local                         :: or: voice-only test with a stub BE, nothing else needed
voice\voice doctor                        :: when something does not work
voice\voice v2                            :: voice chat from any PC (local microphone)
```
Addresses of every page: [../docs/SITI.md](../docs/SITI.md).
