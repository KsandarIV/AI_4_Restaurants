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
