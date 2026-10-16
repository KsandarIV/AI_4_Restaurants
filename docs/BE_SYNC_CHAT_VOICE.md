# Sincronizzazione BE ↔ CHAT ↔ VOICE

Come lavoriamo in 3 senza pestarsi i piedi: il BE possiede DB + LLM, CHAT e VOICE sono client
sottili che parlano SOLO via HTTP LAN. Questo file è il diario condiviso: chi cambia un
comportamento visibile agli altri lo annota in fondo con data e azione richiesta.

## Responsabilità

| Chi | Possiede | Non tocca |
|---|---|---|
| BE (membro 1) | `backend/`, `docs/BE_*.md`, `Dockerfile`, `docker-compose.yml`, `restaurant.db`, modello Ollama | `chat/`, `voice/` |
| CHAT (membro 2) | `chat/` (Streamlit 8501 + servizio 8002 per il sito) | `backend/`, `voice/` |
| VOICE (membro 3) | `voice/` (porta 8003, Whisper + Piper) | `backend/`, `chat/` |

## Flusso condiviso (contratto stabile)

1. **Registrazione** (una volta per cliente): CHAT/VOICE raccolgono nome+telefono e chiamano
   `POST /api/customers` → `customer_id`. Dettagli e validazioni: `docs/BE_API_CONTRACT.md` §1.
2. **Conversazione**: `POST /api/chat { message, session_id, customer_id, client_type }`.
   Il testo inviato deve essere già anonimizzato (niente PII nel `message`).
3. **Conferme**: il BE chiede sempre conferma prima di prenotare/modificare/cancellare.
   I client NON devono interpretare il "sì" al posto del BE: lo rimandano come messaggio.
4. **Avvio demo**: prima il BE (`python -m backend.main` o `docker compose up`), poi chat/voice.
   Stato: `python entrypoint\avvia.py --status` oppure `GET http://<IP_BE>:8000/api/health`.

## Porte e ambienti (non cambiare senza avvisare)

BE `8000` · CHAT `8501` + servizio sito `8002` · VOICE `8003` · Ollama `11434`.
IP e chiavi solo nel `.env` locale (mai commit). `STAFF_API_KEY` resta solo sulla macchina BE.

## Diario modifiche (il più recente in cima)

- **2026-10-15 · BE · transazioni atomiche + WAL** (nessuna azione per CHAT/VOICE):
  `create/modify/cancel` ora usano `BEGIN IMMEDIATE` + `rollback` garantito; connessioni SQLite con
  WAL/`busy_timeout`/FK. Stessi endpoint, stessi JSON. Effetto visibile: meno errori sotto carico,
  nessuna doppia prenotazione sullo stesso tavolo/slot. Test: `python -m pytest tests -q` (147+).
- **2026-10-15 · BE · Docker**: aggiunti `Dockerfile` (solo BE) + `docker-compose.yml`
  (BE + Ollama, volumi `restaurant-data`, `ollama-models`). Uso: `docker compose up --build` sulla
  macchina BE, poi `docker exec <ollama> ollama pull gemma4:12b`. Il deploy via `avvia.py` resta invariato.
- **2026-10-15 · BE · docs/**: creata questa cartella di sincronizzazione (3 file).
  Colleghi: quando cambiate qualcosa che impatta il BE (nuovo campo atteso, nuovo flusso voce),
  aggiungete una riga qui sotto e avvisate.
- **Aperto · VOICE**: passare a `POST /api/customers` prima di prenotare (oggi invia il nome in
  `POST /api/reservations`, rifiutato con registrazione attiva). Workaround demo dichiarato:
  `REQUIRE_CUSTOMER_REGISTRATION=false` sul BE, con controllo proprietario spento.
