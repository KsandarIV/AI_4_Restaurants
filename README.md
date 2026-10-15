# AI 4 Restaurants — Sistema di Prenotazione Ristorante con AI

Sistema distribuito di intelligenza artificiale per la prenotazione di tavoli in un noto ristorante (**Trattoria Bella Napoli**), sviluppato in team di 3 persone:

| Componente | Membro | Descrizione |
|---|---|---|
| **BE** | **Membro 1** | Backend Python con LLM locale (LangGraph, LangChain) e database SQLite (gestione disponibilità, tavoli, menu, prenotazioni) |
| **CHAT** | **Membro 2** | Chatbot testuale che chiama il BE via rete locale (Streamlit / UI di chat) |
| **VOICE** | **Membro 3** | Voicebot vocale che chiama il BE via rete locale (STT Whisper locale + TTS) |

```mermaid
flowchart TD
    subgraph LAN_Clients["Client su Macchine Remote (LAN)"]
        ChatBot["💻 CHAT (Membro 2)<br/>Chatbot testuale"]
        VoiceBot["🎙️ VOICE (Membro 3)<br/>Voicebot vocale (STT + TTS)"]
    end

    subgraph Backend_Server["BE Python (Membro 1) — Host LAN :8000"]
        FastAPI["⚡ FastAPI Server<br/>(CORS abilitato, binding 0.0.0.0)"]
        
        subgraph LangGraph_Engine["LangGraph State Engine"]
            Agent["🤖 Agente LLM<br/>(Prompt specializzato per Chat e Voice)"]
            Tools["🛠️ ToolNode<br/>(Verifica, Prenota, Modifica, Cancella, Menu, Info)"]
            Memory["🧠 SqliteSaver<br/>(Persistenza su SQLite per session_id)"]
        end

        subgraph Local_LLM["LLM Locale"]
            Ollama["🦙 Ollama (llama3.2 / mistral / qwen2.5)<br/>Ambiente 100% LOCALE"]
        end

        subgraph Persistence["Persistenza Dati"]
            SQLite[("🗄️ Database SQLite<br/>(tables, reservations, menu_items, info)")]
        end
    end

    ChatBot -- "HTTP POST /api/chat" --> FastAPI
    VoiceBot -- "HTTP POST /api/chat o /api/chat/stream" --> FastAPI
    FastAPI --> LangGraph_Engine
    Agent <--> Ollama
    Agent <--> Tools
    Tools <--> SQLite
    Agent <--> Memory
```

---

## 📐 Vincoli di Progetto Rispettati

1. **Tre macchine separate (LAN)**: Il BE ascolta su `0.0.0.0:8000` con CORS aperto a tutte le origini LAN.
2. **Comunicazione via rete**: API REST e Streaming SSE su HTTP JSON documentate via Swagger su `/docs`.
3. **Privacy / PII (vincolo rivisto dal gruppo)**: nome e telefono servono al ristorante per contattare il cliente, quindi CHAT e VOICE li raccolgono *prima* della conversazione e li inviano **solo** a `POST /api/customers`, che li salva nella tabella `customers` e restituisce un `customer_id` anonimo. L'LLM vede soltanto quel `customer_id` e il `booking_code` (es. `RES-9A8B2C`): nome e telefono non entrano mai nel suo contesto né nei risultati dei tool. Il testo libero della conversazione resta anonimizzato dai client. Vedi "Registrazione dei clienti".
4. **Modelli 100% Locali**: Modelli LLM eseguiti localmente tramite **Ollama** (es. `llama3.2`, `mistral`).
5. **Persistenza & Concorrenza**: Stato conversazionale salvato su SQLite tramite `SqliteSaver` (resiste ai riavvii del server) e lock di concorrenza su transazioni di prenotazione.

---

## 🎯 Casi d'Uso Supportati

1. **Prenotazione di un tavolo**:
   - Assegnazione automatica del tavolo ottimale in base al numero di persone (2, 4, 6, 8, 10 posti) e sala desiderata (*interno, terrazza, giardino*).
   - **Gestione a slot di 90 minuti (Rotazione tavoli)**: Il tavolo non viene bloccato per l'intera serata, ma per esattamente 90 minuti dall'inizio della prenotazione. Questo permette al ristoratore di accogliere più turni (es. alle 19:30 e alle 21:00 sullo stesso tavolo).
   - Controllo rigoroso degli orari (*Pranzo 12:00-15:00 con ultimo arrivo alle 14:00*, *Cena 19:00-23:30 con ultimo arrivo alle 22:00*).
   - Validazione delle date (rifiuto date passate, formato errato e *Lunedì giorno di chiusura*).
   - Generazione del codice di prenotazione univoco (es. `RES-9A8B2C`) collegato al `customer_id` anonimizzato.
2. **Modifica di una prenotazione**:
   - Ricerca tramite codice di prenotazione.
   - Modifica di data, orario, numero coperti e note speciali, con ricalcolo e riassegnazione automatica del tavolo.
3. **Cancellazione di una prenotazione**:
   - Cancellazione tramite codice univoco e immediata liberazione del tavolo.
4. **Consultazione del menu**:
   - Ricerca piatti per categoria (*Antipasti, Primi, Secondi, Contorni, Dessert, Bevande*).
   - Filtro per esigenze alimentari e intolleranze (*senza glutine, vegetariano, vegano, allergeni specifici*).
5. **Richiesta informazioni generali**:
   - Indirizzo, orari di apertura, parcheggio convenzionato (*Garage Toledo*), accessibilità disabili, seggioloni bimbi e policy animali domestici.

---

## 🚀 Guida Rapida all'Installazione

### 1. Prerequisiti
- **Python 3.10+** (verificato con Python 3.11 e Python 3.14)
- **Ollama** installato in locale ([scarica Ollama](https://ollama.com/download))

### 2. Configurazione Ambiente
```bash
# Entra nella cartella del progetto
cd AI_4_Restaurants

# Crea l'ambiente virtuale
python -m venv venv

# Attiva l'ambiente virtuale
# Su Windows PowerShell:
.\venv\Scripts\Activate.ps1
# Su Linux/macOS:
source venv/bin/activate

# Installa le dipendenze
pip install -r requirements.txt
```

### 3. Configurazione Modello Locale (Ollama)
Scarica ed avvia il modello scelto con Ollama:
```bash
ollama run llama3.2
```
Il file `.env` è già configurato di default:
```env
HOST=0.0.0.0
PORT=8000
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
```

### 4. Avvio del Backend
```bash
python -m backend.main
```
All'avvio, il backend:
- Crea automaticamente il database SQLite (`backend/restaurant.db`).
- Inserisce i tavoli (da 2 a 10 posti), il menu completo e le informazioni sul locale.
- Avvia il server su `http://0.0.0.0:8000`.
- Rende disponibile l'interfaccia interattiva Swagger su `http://localhost:8000/docs`.

---

## 📡 Contratti API per CHAT (Membro 2) e VOICE (Membro 3)

| Metodo | Endpoint | Descrizione |
|---|---|---|
| `GET` | `/health` o `/api/health` | Healthcheck del backend |
| `POST` | `/api/customers` | **Da chiamare prima della chat**: registra nome e telefono, ritorna `{ customer_id }` |
| `POST` | `/api/chat` | Chat conversazionale JSON (ritorna `{ reply, session_id }`) |
| `POST` | `/api/chat/stream` o `/chat/stream` | Streaming SSE per voice bot (`data: {"token": "..."}`) |
| `GET` | `/api/availability` | Query parametri: `date`, `time`, `party_size` |
| `POST` | `/api/reservations` | Crea prenotazione (`date`, `time`, `party_size`, `customer_id` registrato). Il campo `name` è ignorato. |
| `GET` | `/api/reservations/{booking_code}?customer_id=...` | Dettagli prenotazione (solo del proprietario) |
| `PATCH`/`PUT` | `/api/reservations/{booking_code}` | Modifica data, ora o numero persone (body con `customer_id` del proprietario) |
| `DELETE` | `/api/reservations/{booking_code}?customer_id=...` | Cancella prenotazione (solo del proprietario) |
| `GET` | `/api/menu` | Elenco piatti con filtri allergeni/diete |
| `GET` | `/api/info` | Orari, indirizzo, parcheggio, servizi |

### Registrazione dei clienti
```json
POST /api/customers
{ "name": "Mario Rossi", "phone": "+393331234567", "consent": true }

200 → { "customer_id": "cust_8f3a1c9d2b4e" }
422 → dati non validi (telefono non in formato internazionale E.164, nome vuoto, consenso mancante)
```
Il client usa poi quel `customer_id` in tutte le chiamate (`/api/chat`, prenotazioni). Con `REQUIRE_CUSTOMER_REGISTRATION=true` (predefinito):
- si può prenotare solo con un `customer_id` registrato (un `customer_id` anonimo, es. `anon_...`, può solo chiedere menu e informazioni);
- solo il cliente che ha fatto una prenotazione può leggerla, modificarla o cancellarla: per tutti gli altri il codice risulta "non trovato";
- nei tool dell'LLM il `customer_id` viene sempre preso dalla sessione, mai da ciò che scrive il modello.

Con `REQUIRE_CUSTOMER_REGISTRATION=false` il BE torna al comportamento precedente (nessuna registrazione né controllo). **Il voicebot** oggi invia il nome in `POST /api/reservations` senza registrare il cliente: finché non usa `/api/customers` le sue prenotazioni vengono rifiutate con la registrazione attiva.

### Esempio chiamata Chat standard:
```json
POST /api/chat
{
  "message": "Vorrei prenotare per 4 persone domani alle 20:30",
  "session_id": "sess_123",
  "customer_id": "anon_user_abc",
  "client_type": "chat"
}
```

### Script Client di Test per la Rete LAN
È disponibile `client_demo.py` che i compagni possono lanciare per testare subito il BE da un'altra macchina:
```bash
python client_demo.py http://<IP_MACCHINA_BE>:8000
```

---

## 🛠️ Sicurezza, area del ristoratore e manutenzione

**Conferma prima di agire.** Il modello linguistico può solo *proporre* una prenotazione, modifica o cancellazione: il BE risponde con un riepilogo scritto dal codice ("Tavolo per 4 persone venerdì 16 ottobre alle 20:30. Confermi?") ed esegue solo dopo un "sì" esplicito. "Sì ma alle 21" non è una conferma. Una richiesta impossibile (giorno chiuso, orario fuori servizio, nessun tavolo, troppi ospiti) non viene nemmeno proposta, e una prenotazione si propone solo se negli ultimi messaggi c'è una richiesta di prenotare.

**Allergie e intolleranze.** Le domande su allergie, intolleranze o "senza glutine/lattosio…" **non passano dal modello**: la risposta è costruita dal codice con i piatti del database (`backend/graph/allergies.py`). Per un allergene non presente nel menu (es. arachidi) il BE dice di non avere informazioni e rimanda al personale. Il filtro `allergen_free` riconosce sinonimi (latticini, latte → lattosio) e rifiuta le parole sconosciute invece di restituire tutto il menu.

**Area staff per il ristoratore.** Imposta `STAFF_API_KEY` nel `.env` e apri `http://<IP_BE>:8000/api/staff`: pagina con le prenotazioni (data, ora, persone, tavolo, **nome e telefono** del cliente, note), filtrabili per data e stato. Senza chiave l'area è disabilitata. Endpoint (header `X-API-Key`):

| Metodo | Endpoint | Cosa fa |
|---|---|---|
| `GET` | `/api/staff/reservations?date=&status=` | Prenotazioni con nome e telefono del cliente |
| `GET` / `POST` | `/api/staff/closures` | Elenco / nuova chiusura straordinaria `{date, reason}` (le prenotazioni già fatte **non** vengono cancellate: la risposta le elenca) |
| `DELETE` | `/api/staff/closures/{data}` | Riapre il ristorante in quella data |
| `PATCH` | `/api/staff/menu/{id}` | `{available: false}` = piatto esaurito (sparisce dal menu); oppure cambia il prezzo |

Nome e telefono compaiono **solo** qui: mai nelle risposte destinate ai clienti né al modello.

**Menu.** Ogni piatto ha un tipo (`carne`, `pesce`, `vegetale`, `dolce`, `bevanda`): `GET /api/menu?dish_type=carne` e il tool `get_menu(dish_type=...)`. Le categorie accettano sinonimi (`dolci` → Dessert).

**Dati sempre allineati.** All'avvio il BE aggiunge le colonne mancanti ai database vecchi e riallinea menu e informazioni con `backend/database/seed_data.py` (aggiorna i piatti esistenti, aggiunge i nuovi, non cancella nulla e rispetta i piatti segnati come esauriti). Gli orari mostrati al cliente sono generati dalla configurazione: non possono più contraddire le regole di prenotazione.

**Errori e salute del servizio.** Con Ollama spento o troppo lento `/api/chat` risponde **503** con un messaggio chiaro; ogni altro errore è un 500 senza dettagli interni (il dettaglio resta nel log). `/api/health` controlla davvero database, server del modello e presenza del modello configurato: `status` è `online` o `degraded`.

**Dati personali nel tempo.** `python -m backend.maintenance purge --dry-run` mostra quanti clienti verrebbero cancellati; senza `--dry-run` cancella nome e telefono di chi è registrato da più di `DATA_RETENTION_DAYS` giorni (predefinito 90) e non ha prenotazioni recenti. Le prenotazioni restano, anonime.

**Scelta e verifica del modello.** Il BE sceglie il modello da solo (vedi `OLLAMA_MODEL`), lo scrive nel log e lo mostra in `/api/health`. `python -m backend.check_model` fa una breve conversazione di prova (saluto, orari, menu, prenotazione con conferma, frase senza senso) su un database temporaneo e stampa OK/KO con i tempi; con `--model nome` si prova un altro modello. Va eseguito prima della demo e a ogni cambio di modello.

**Backup e chiave staff.** `python -m backend.maintenance backup` copia il database in `backend/backups/` (tiene gli ultimi 14); `python -m backend.maintenance staff-key` genera una chiave casuale da mettere nel `.env`.

**Messa in produzione.** Checklist della prova generale sulle tre macchine e scaletta delle presentazioni: [PRODUZIONE.md](PRODUZIONE.md).

**Vedere il database.** File `backend/restaurant.db` (SQLite): aprirlo in sola lettura con *DB Browser for SQLite*, oppure usare la pagina staff.

**Impostazioni** (variabili d'ambiente o `.env`, vedi `.env.example`):

| Variabile | Predefinito | Significato |
|---|---|---|
| `STAFF_API_KEY` | vuota | Chiave dell'area staff (vuota = disabilitata) |
| `REQUIRE_CUSTOMER_REGISTRATION` | `true` | Prenotare richiede un cliente registrato; solo il proprietario vede/modifica/cancella |
| `OLLAMA_MODEL` | `gemma4:12b` | Modello, o elenco in ordine di preferenza (`gemma4:12b,gemma4-coder`): si usa il primo installato in Ollama **che sappia usare gli strumenti** |
| `OLLAMA_FALLBACK_MODELS` | `gemma4-coder,llama3.2` | Ripieghi se nessuno dei preferiti è installato (così ogni macchina funziona con i modelli che ha) |
| `OLLAMA_REASONING` | vuota = spento | "Thinking" dei modelli che ragionano: spento = risposte in 4-7 s invece di 10-30. `true` solo se il modello lo supporta |
| `OLLAMA_KEEP_ALIVE` | `30m` | Quanto Ollama tiene il modello in memoria; il BE lo carica all'avvio |
| `OLLAMA_TIMEOUT_S` | `120` | Dopo quanti secondi il modello è considerato non raggiungibile |
| `CLOSED_WEEKDAYS` | `0` | Giorni di chiusura settimanale (0 = lunedì … 6 = domenica) |
| `CORS_ORIGINS` | `*` | Origini web ammesse, separate da virgola |
| `DEBUG` | `false` | `true` = riavvio automatico a ogni modifica dei file: solo per sviluppare |
| `DATA_RETENTION_DAYS` | `90` | Conservazione di nome e telefono |
| `CHECKPOINTS_DB_PATH` | `backend/conversations.db` | Dove si salvano le conversazioni |

**Limiti noti.** Il lucchetto contro le doppie prenotazioni vale per un solo processo del server (non avviare più worker). Un modello piccolo come `llama3.2` può sbagliare nelle risposte libere (per esempio attribuire allergeni sbagliati a un piatto nel menu generico): le allergie sono protette dal codice, il resto no. Nessuna autenticazione sugli altri endpoint, adatto a una rete LAN.

---

---

## 🧪 Esecuzione della Suite di Test

Tutti i test (DB, Tools, LangGraph, API REST, staff, allergie, conferme, validazioni) si eseguono dalla radice del progetto:
```bash
python -m pytest tests -q
```
Scrivere `tests` è importante: senza, pytest raccoglie anche `voice/` e va in errore se il pacchetto `voicebot` non è installato.
I test usano un database **temporaneo** (cartella creata e cancellata da `tests/conftest.py`) e il modello finto: non toccano `backend/restaurant.db` e non richiedono Ollama.

---

## 👥 Guida alla Presentazione per gli Stakeholder

### 1. Presentazione al Responsabile Tecnico
- **Architettura LangGraph**: Grafo degli stati in `backend/graph/workflow.py`, `ToolNode`, `tools_condition` e `SqliteSaver` per la persistenza su disco del contesto multi-turno.
- **Privacy e Conformità Vincoli**: PII gestite tramite token anonimi (`customer_id`) e modello LLM locale al 100% su Ollama.
- **Integrità del Database e Concorrenza**: Lock thread-safe per prevenire race conditions e calcolo della rotazione oraria di 90 minuti.
- **Documentazione OpenAPI**: Swagger UI su `http://localhost:8000/docs`.

### 2. Presentazione al Ristoratore
- **Esperienza Utente Naturale**: Conversazione fluida in italiano, con prompt specializzato sintetico per la voce (TTS) ed esauriente per la chat.
- **Regole di Business**: Chiusura del Lunedì, finestre di arrivo pranzo e cena, rispetto della capienza tavoli e menu tipico con allergeni e opzioni senza glutine/vegetariane.
