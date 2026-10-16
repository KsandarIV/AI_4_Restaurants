# HANDOFF — passaggio di lavoro tra membri e AI (template + regole)

Ogni passaggio (umano→umano, umano→AI, AI→umano) si chiude con un handoff scritto:
o qui sotto come sezione datata, o nel messaggio di commit/PR. Niente handoff = lavoro non finito.

## Template (copia e compila)

```md
## Handoff YYYY-MM-DD — da X a Y
Stato: [fatto | in corso | bloccato]
Fatto: ...
Da fare: ...
Come testare: (comandi esatti)
Branch/commit: ...
Attenzione: (conflitti noti, file sporchi, cose da non toccare)
```

## Regole

1. Un handoff per consegna, max 15 righe di sostanza + comandi copiabili.
2. Sempre: branch/commit esatto e comando di verifica (quello di `docs/AGENTS.md` §3).
3. Se tocchi cartelle condivise, dillo esplicitamente ("ho toccato setup/lan/entrypoint perché...").
4. Istruzioni differenti per macchina diversa vanno nel template (BE/CHAT/VOICE).
5. Il ricevente conferma con un `--status` o test verde prima di dichiararlo chiuso.

## Handoff 2026-10-15 — da VOICE a team
Stato: fatto (da verificare sulle altre macchine)
Fatto: voice v1+v2, `/prova-vocale`, `/tech`, stub BE, requirements per-ruolo,
entrypoint unico, lan con identità multi-servizio, docs/ (FLUSSO/AGENTS/HANDOFF).
Come testare: `cd voice && ..\.venv\Scripts\python -m pytest tests -q` (18 test);
`python entrypoint\avvia.py --attendi` dal presentatore.
Branch/commit: su `savov`, da fondere in `main`.
Attenzione: `lan/macchina.json` e `.env` sono locali per macchina (mai in git);
`voice/models/` ignorato; primo `setup --role <ruolo>` per macchina.

## Handoff 2026-10-15 (evening) — VOICE rework (English), from VOICE to team
Status: done and verified locally; **not yet tried on the three machines**.
Done: the voice bot now behaves exactly like the chat bot (registration by voice -> `POST /api/customers`,
same anonymiser and `[TYPE_N]` placeholders, BE `/api/chat` + `/api/chat/stream`, no local shortcuts).
v1 live and v2 on-demand share one engine. Fixed: Piper 1.8 API (TTS never worked with the real model),
VAD pause timing with browser chunks (was 6x too long), models reloaded per call, barge-in could not cancel a
thinking turn, tests failing under the system Python. New: `python -m voicebot.doctor`, `/diag`, `live_client`
(mic without browser, auto-reconnect), English prompt `voice/src/voicebot/prompts.py`, `voice/Dockerfile`.
To do (BE team): make `backend/graph/prompts.py` voice prompt match `voice/src/voicebot/prompts.py`; the BE reads only
the last user message, so the system prompt sent by VOICE is a specification, not yet an instruction.
How to test: `cd voice && ..\.venv\Scripts\python -m pytest tests -q` (~120 tests), `python -m mypy src`,
`python -m voicebot.doctor`; manual: `python -m voicebot` then http://localhost:8003/prova-vocale.
Shared files touched: `.env.example` (VOICE section only), `setup/requirements/voice.txt` (+phonenumbers),
`setup/requirements/dev.txt` (+mypy), `docs/FLUSSO.md` (voice sections). Re-run `python entrypoint\avvia.py`
on the VOICE machine to install `phonenumbers`. Default `STT_MODEL` is now `small` (downloaded on first start).
Attention: `.env` on the VOICE machine may still contain old `LLM_SYSTEM_PROMPT` / `STT_MODEL=tiny` lines.

## Handoff 2026-10-15 (night) — VOICE: commands, site, spoken report, from VOICE to team
Status: done and tested locally (150+ tests, mypy strict, real Whisper/Piper against the stub BE); **three-machine run not yet tried**.
New: `voice\voice local` = complete local test (stub BE + voice + browser, banner "LOCAL TEST"); the real flow is still
`python entrypoint\avvia.py`; also `voice\voice real|doctor|v2|live|test` (= `python -m voicebot <cmd>`).
New: voice site at `http://VOICE:8003/` (same look as `frontend/`, copied CSS) with the assistant and **My reservations**
(live status from `GET /api/reservations/{code}?customer_id=`, only the owner can read a code).
New: after a booking/change/cancellation the bot reads the real data back by voice and asks a last yes
(built by code, not by the LLM; "yes, but..." goes to the agent as a change request).
Fixed: a phone number cut in two utterances by a pause is joined; Whisper prompt off by default (it was echoed back).
Shared files touched: `docs/FLUSSO.md`, `docs/HANDOFF.md`, `.env.example` (VOICE section). The BE was not touched.
Attention: the BE has no "list my reservations" endpoint, so the page keeps the codes of this browser (localStorage);
a `GET /api/customers/{id}/reservations` would let any browser show them all (BE team decision).

## Handoff 2026-10-15 (late) — VOICE: lazy registration, Italian prompt, booking pop-up, from VOICE to team
Changed (voice only): the call opens with a short welcome ("Come posso aiutarla?"); name + phone are asked only when the caller
talks about booking, then the original request is replayed to the BE. Agent prompt is now Italian (`voice/src/voicebot/prompts.py`),
multilingual by the customer's language, asks about a room before confirming. The site shows a rounded booking pop-up closed
4 s after the spoken final yes; orb without halo/ring/hint text; live transcript only in local test mode. ~166 tests.
To do (BE team): adopt the voice prompt in `backend/graph/prompts.py`; "ask the surname only when a similar booking exists"
needs the BE (voice cannot see other customers' bookings); the BE assigns a room even when none is asked.

## Handoff 2026-10-15 (night 2) — VOICE: weak-PC mode, context windows, from VOICE to team
New (voice only): the voice bot refreshes the BE session every 20 exchanges (spoken recap), warns at the 3rd refresh and ends
the call at the 4th (`call_ended`); start-up warm-up turn to the BE (`WARM_BACKEND`); `voice/local_llm/Modelfile` = same gemma4
with an 8k context for weak PCs. Measured on a laptop CPU: first BE turn ~70 s, next ones ~3 s. ~172 tests.
To do (BE team): in that run the BE answered some turns with text like "Chiamo get_menu con is_vegetarian=true." instead of
executing the tool (8B model, long prompt) - worth checking `backend/graph`; the BE could also warm its own prompt at start-up and
set `num_ctx` explicitly.
New (voice only): `voice/src/voicebot/toolguard.py` drops and retries BE replies that name tools or ask a pointless permission (workaround; the cause is in the BE prompt/model).
Changed (voice only): the voice site's "Prenota a voce" button now turns into the orb (no panel, no transcript), a "Scrivi" chat window
was added (proxy `/site/chat/*` to `CHAT_SERVICE_URL`, off here), the test page is `/test-voice` (old `/prova-vocale*` redirect),
and the command names in these docs (`voice\voice`, `entrypoint\avvia.py`) were restored (control characters had eaten the backslashes).
To do (BE team), found while measuring on a laptop CPU: `backend/graph/prompts.py` writes the date and the `customer_id` (and the "not registered" block)
near the TOP of the system prompt, so Ollama's prompt cache is lost at every new customer and every new day: the first turn of a
customer costs about a minute on a weak CPU, the next ones 1-3 s. Moving the per-customer/per-day lines to the END of the prompt would
keep the long part (rules + tools) cached. Voice-side workaround: all unregistered callers share the id `anon_voice`, and a start-up warm-up turn
pays the cost once (`WARM_BACKEND`). Also: some replies announce instead of answer ("Posso mostrarle i piatti...", "Chiamo get_menu...");
`voice/src/voicebot/toolguard.py` drops and retries them once.

## 2026-10-16 — VOICE: materiale di presentazione
`docs/studio/voice/`: `PRESENTAZIONE.md` (copione passo per passo) + 4 mini-presentazioni PDF (stack/venv/LAN, flusso del codice, storia e fix da git, il BE e i punti di contatto) + `00_presentazione_completa.pdf` (47 slide). Sorgenti in `_sorgenti/` (`python build.py`, serve solo Edge/Chrome).
To do (BE team), emerso preparandole: `/api/chat/stream` e' `async` ma chiama `process_message` in modo bloccante (il BE non risponde nemmeno a `/api/health` mentre l'LLM lavora).
Aggiunti in `docs/studio/voice/`: `MANUALE_TECNICO.md` (comandi per componente, test, sessioni live, configurazioni di avvio), `flowchart_flusso_codice.svg` (+ `05_flowchart_verticale.pdf`), sezione sull'entrypoint in `entrypoint/README.md`.

## Handoff 2026-10-16 — siti della demo automatici (cartella `showcase/`), da VOICE a team
Stato: fatto; da provare sulle tre macchine con `python entrypoint\avvia.py`.
Fatto: all'avvio si aprono da soli i siti: BE `solo-be.localhost:8080` + `completo.localhost:8090`, CHAT `chat.localhost:8080`
(parte da solo `http.server` su `frontend/`), VOICE `voce.localhost:8003/test-voice`. Il sito completo e' il sito voce
(orb animato + finestrella chat + prenotazioni) servito in locale da `showcase/serve.py` e puntato al PC voce.
File condivisi toccati: solo `lan/machine_setup.py` (un blocco in `start_component`, errore = solo un log) e docs.
NON toccati: `frontend/`, `chat/`, `backend/`. Server voce: CORS aperto (`allow_origins=["*"]`, rete di demo).
Attenzione: `frontend/js/config.js` ha `be.baseUrl` fisso su un IP (10.10.95.34): se il BE cambia IP va aggiornato
(file di chi cura il frontend). Per non andare in conflitto: ognuno solo la sua cartella, `git pull --rebase` prima di pushare.

## Handoff 2026-10-16 (pomeriggio) — LAN: scoperta dei servizi e siti su tutte le macchine, da VOICE a team
Causa del "la chat non funziona sul sito completo": il lanciatore usava gli IP di esempio di `lan/lan_config.json` (192.168.1.x)
invece di quelli reali (10.10.x.x). Ora gli indirizzi dei peer sono verificati e riscoperti (`showcase/peers.py`, cache
`lan/peers.json` ignorata da Git); il sito completo li rilegge a ogni caricamento. Il sito completo ora ha anche l'Area ristoratore
(`/staff.html`, dati dal BE reale), Swagger e salute del BE; si apre su tutte le macchine insieme alla pagina di test del ruolo.
Se un servizio vecchio occupa 8003/8080/8090 il lanciatore lo segnala invece di tacere.
Operatore: `python -m showcase.peers show|scan|set`. Elenco di tutti i siti: `docs/SITI.md`.
Branch: tutti su `savov` finche' non e' in `main` (vedi sotto); nessuno committa direttamente su `savov` se non il proprietario.

## Handoff 2026-10-16 (sera) — topologia a stella: il sito completo parte dal BE (gateway), da VOICE a team
Regola della traccia applicata: CHAT e VOICE parlano solo con il BE. Il sito completo e' servito dal **gateway sul BE**
(`showcase/gateway.py`, https :8090, reverse proxy): `/api/*` e `/docs` -> BE (database, area ristoratore), `/voice/*` + WebSocket -> PC VOICE,
`/voice/site/chat/*` -> PC CHAT. I PC CHAT e VOICE aprono `https://<IP-BE>:8090/` (certificato autofirmato: "Avanzate -> Procedi" una volta).
HTTPS serve per il microfono; `cryptography` e' ora in `setup/requirements/be.txt` (rilanciare `avvia.py` sul BE). Il PC voce non chiama piu' la chat.
Verificato: wss attraverso il gateway verso un server voce reale (ready + audio), BE reale proxato, 230 test.
