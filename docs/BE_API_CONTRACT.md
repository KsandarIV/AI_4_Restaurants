# Contratto API del BE per CHAT e VOICE (rete LAN)

Base URL: `http://<IP_BE>:8000`. Swagger: `http://<IP_BE>:8000/docs`.
Tutti gli endpoint esistono sia con prefisso `/api/...` sia senza (alias radice per compatibilità,
nascosti dallo schema). JSON ovunque. Errori: `{ "detail": "..." }` senza dettagli interni.

> Regola d'oro privacy: nome e telefono del cliente viaggiano SOLO verso `POST /api/customers`.
> In ogni altra chiamata si usa il `customer_id` anonimo restituito. L'LLM non vede mai i PII.

## 1. Registrazione cliente (PRIMA della conversazione)

```
POST /api/customers
{ "name": "Mario Rossi", "phone": "+393331234567", "consent": true }

200 → { "customer_id": "cust_8f3a1c9d2b4e" }
422 → telefono non E.164 / nome vuoto / consenso mancante
```

Il `customer_id` va riusato in `/api/chat` e nelle prenotazioni dirette.
Con `REQUIRE_CUSTOMER_REGISTRATION=true` (default): senza `customer_id` registrato non si
prenota; solo il proprietario può leggere/modificare/cancellare le sue prenotazioni
(agli altri il codice risulta "non trovato").

## 2. Conversazione (LLM + tool deterministici)

```
POST /api/chat
{ "message": "...", "session_id": "sess_123", "customer_id": "cust_...", "client_type": "chat|voice" }
→ { "reply": "...", "session_id": "...", "customer_id": "...", "client_type": "...", "timestamp": "..." }
```

- `session_id`: lo genera il client, identifica la conversazione (memoria multi-turno su SQLite).
- `customer_id`: usato dai tool come identità, MAI chiesto al modello.
- Errori: `503` = Ollama spento/lento ("modello non risponde"); `500` = errore interno generico.

Streaming SSE (voicebot): `POST /api/chat/stream` (o `/chat/stream`) con
`{ "message" | "messages": [{role, content}], "session_id", "customer_id", "client_type" }`.
Risponde `data: {"token": "..."}` parola per parola + `data: [DONE]`.

## 3. Prenotazioni dirette (senza LLM)

| Metodo | Endpoint | Note |
|---|---|---|
| `GET` | `/api/availability?date=AAAA-MM-GG&time=HH:MM&party_size=N` | `→ { available, tables_count, ... }` (`guests` è alias di `party_size`) |
| `POST` | `/api/reservations` | `{ date, time, guests\|party_size, customer_id, special_requests?, preferred_location? }`. Il campo `name` è ignorato. `400` se impossibile. |
| `GET` | `/api/reservations/{booking_code}?customer_id=...` | Solo proprietario. `404` se assente o di altri. |
| `PATCH`/`PUT` | `/api/reservations/{booking_code}` | Body `{ new_date?, new_time?, new_guests?\|party_size?, new_requests?, customer_id }`. `400` se impossibile. |
| `DELETE` | `/api/reservations/{booking_code}?customer_id=...` | Idempotente. `404` se assente o di altri. |

## 4. Menu e info

- `GET /api/menu?category=&allergen_free=&is_vegetarian=&is_vegan=&is_gluten_free=&dish_type=`
  → lista piatti. `allergen_free` con allergene sconosciuto → `400` (mai "nessun piatto lo contiene").
- `GET /api/info?key=` → tutto il dizionario, oppure una sola voce
  (`address`, `opening_hours`, `phone`, `email`, `parking`, `services`, `payment_methods` + alias IT).

## 5. Salute e area staff

- `GET /api/health` (o `/health`) → `{ status: online|degraded, restaurant, llm_provider,
  llm_model, database, llm_reachable, llm_model_available }`.
- Area staff (solo ristoratore, header `X-API-Key: <STAFF_API_KEY>`, pagina su `/api/staff`):
  `GET /api/staff/reservations?date=&status=`, `GET|POST /api/staff/closures`,
  `DELETE /api/staff/closures/{data}`, `PATCH /api/staff/menu/{id}` (`{available, price}`).
  Nome e telefono compaiono SOLO qui.

## Changelog per CHAT/VOICE

- 2026-10-15 (BE): nessuna modifica al contratto. Resa atomica la scrittura prenotazioni
  (BEGIN IMMEDIATE + WAL, vedi `docs/BE_DB_SCHEMA.md`); stesso comportamento, meno `500`/overbooking
  sotto carico. Nessuna azione richiesta ai client.
- Nota nota: il voicebot deve passare a `POST /api/customers` prima di prenotare, altrimenti con la
  registrazione attiva le sue prenotazioni sono rifiutate (`REQUIRE_CUSTOMER_REGISTRATION=true`).
