# AGENTS — istruzioni per gli assistenti AI (umani: fattele leggere al vostro LLM)

Questa repo è lavorata da 3 persone + i loro LLM (vibe coding). Chiunque (umano o AI)
modifica codice qui dentro rispetta queste regole. Prima di toccare codice condiviso,
l'AI deve aver letto `docs/FLUSSO.md` e questa pagina.

## 1. Proprietà cartelle

| Cartella | Owner | Altri possono? |
|---|---|---|
| `backend/` | team BE (2 persone) | No (solo leggere per il contratto API) |
| `chat/`, `frontend/` | membro CHAT | No (solo leggere) |
| `voice/` | membro VOICE | No (solo leggere) |
| `setup/`, `lan/`, `entrypoint/`, `docs/` | CONDIVISE | Sì, ma vedi §2 |

## 2. Regole per il codice condiviso

1. Mai rompere i 3 comandi: `setup_env.py --check-only`, `avvia.py --status`, `pytest voice/tests -q`.
2. Solo stdlib in `setup/`, `lan/`, `entrypoint/` (devono girare a venv rotto).
3. Mai committare: `.env`, `.venv/`, `lan/macchina.json`, `voice/models/`, `*.db`, log.
4. Mai `push --force` su `main`; mai `reset --hard` senza backup dichiarato.
5. Ogni modifica condivisa: verifica con compile + comando relativo, e scrivilo nel messaggio.
6. Il contratto BE (`backend/api/routes.py`) è l'unica verità API: se cambia, aggiornare
   `voice/tests/stub_be.py` e `docs/FLUSSO.md` nello stesso push.

## 3. Comandi di verifica (Windows, da root se non detto)

```bat
python setup/setup_env.py --check-only
python entrypoint/avvia.py --status
python -m py_compile <file modificato>
cd voice && ..\..venv\Scripts\python -m pytest tests -q
```

## 4. Porte e salute (non cambiarle senza accordo a tre)

BE 8000 (`/api/health`) · sito 8080 (`/`) · chat 8501 (`/_stcore/health`) ·
chat-api 8002 (`/health`) · voice 8003 (`/health`, WS `/ws/voice`, test `/test-voice`, tech `/tech`).
