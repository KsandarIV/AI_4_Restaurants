# Schema DB e garanzie di concorrenza (BE, SQLite)

File: `backend/restaurant.db` (conversazioni: `backend/conversations.db`, via `SqliteSaver`).
ORM: SQLAlchemy declarative (`backend/database/models.py`). Seed + riallineamento a ogni avvio
(`backend/database/seed_data.py`, idempotente: non cancella mai nulla, rispetta `available=false`).

## Tabelle

| Tabella | Colonne chiave | Note |
|---|---|---|
| `tables` | `id, table_number UNIQUE, capacity, location (interno/terrazza/giardino), is_active` | 12 tavoli, 2–10 posti |
| `reservations` | `id, booking_code UNIQUE (RES-XXXXXX), customer_id (token anonimo, indice, NO FK voluta), table_id → tables, date (AAAA-MM-GG, indice), time (HH:MM), shift (pranzo/cena), guests_count, status (CONFIRMED/CANCELLED), special_requests` | Cancellazione = cambio stato (storico conservato) |
| `customers` | `id, customer_id UNIQUE (cust_...), name, phone (E.164), consent_at, created_at` | UNICO punto con PII. Mai letto dall'LLM (solo area staff). `purge` cancella i contatti > `DATA_RETENTION_DAYS` gg senza prenotazioni recenti; le prenotazioni restano, anonime |
| `menu_items` | `id, category, name, description, price, allergens (csv), is_vegetarian/vegan/gluten_free, dish_type (carne/pesce/vegetale/dolce/bevanda), available (esaurito)` | Solo `available`/`price` mutabili a runtime (staff) |
| `restaurant_info` | `key UNIQUE, value, description` | Orari generati da `config.py`: non possono contraddire le regole |
| `closures` | `date UNIQUE, reason` | Chiusure straordinarie (oltre `CLOSED_WEEKDAYS`, default lunedì) |
| `schema_version` | `version` | Versione migrazioni (vedi sotto) |

## Regole di business (applicate nel codice, non delegate all'LLM)

- Slot di **90 minuti** (`RESERVATION_DURATION_MINUTES`): overlap = `max(inizi) < min(fini)`.
- Finestre: pranzo 12:00–15:00 (ultimo arrivo 14:00), cena 19:00–23:30 (ultimo arrivo 22:00).
- Date: no passato, no lunedì (configurabile), no `closures`, max +120 gg.
- Gruppi oltre la capienza max → risposta con telefono del locale, mai proposta di prenotazione.
- L'LLM **propone**, il codice **decide**: prenotazione/modifica/cancellazione eseguite solo dopo
  "sì" esplicito a un riepilogo scritto dal codice. Allergie: risposta costruita dal codice
  (`backend/graph/allergies.py`), allergene sconosciuto → si rimanda al personale.

## Concorrenza e anti-overbooking (aggiornato 2026-10-15)

1. **WAL** (`PRAGMA journal_mode=WAL` in `connection.py`): letture (menu/info) non bloccano scritture.
2. **`busy_timeout=5000`**: uno scrittore concorrente attende invece di fallire `SQLITE_BUSY`.
3. **`synchronous=NORMAL` + `foreign_keys=ON`**.
4. **`table_lock` (thread)** + **`BEGIN IMMEDIATE` (DB)** in `create/modify/cancel_reservation`:
   il controllo disponibilità + inserimento/aggiornamento è UNA transazione atomica;
   ogni `return` di errore dentro la transazione fa `rollback` (non si lascia mai il lock di scrittura
   appeso); eccezioni impreviste → `rollback` + errore generico (dettagli solo nel log).
5. `booking_code` generato con controllo unicità su DB.
- Limite noto (invariato): un solo processo worker (`uvicorn` senza `--workers`); il lock
  thread vale in-process, `BEGIN IMMEDIATE` serializza anche scrittori di processi diversi su SQLite,
  ma il deploy supportato resta a processo singolo.

## Migrazioni

`Base.metadata.create_all()` + registro versionato in `crud.py` (`_SCHEMA_MIGRATIONS`, `migrate_schema()`,
tabella `schema_version`): passi idempotenti basati su `PRAGMA table_info`, eseguiti da `init_db()`.
Versione corrente: **v2** (`menu_items.dish_type`, `menu_items.available`).
Nota per il responsabile tecnico: Alembic valutato e differito di proposito (file singolo, 1 writer,
2 colonne post-v1); i modelli sono `declarative` standard, quindi `alembic init` + autogenerate
è adottabile senza toccare `crud.py` quando le migrazioni supereranno ~10.

## Backup e ispezione

- `python -m backend.maintenance backup` (copia online via `sqlite3.backup`, tiene ultimi 14 in `backend/backups/`).
- DB apribile in sola lettura con DB Browser for SQLite; oppure pagina staff.
- Ripristino pulito: spegni il BE, cancella `backend/restaurant.db*` e `backend/conversations.db*`.
