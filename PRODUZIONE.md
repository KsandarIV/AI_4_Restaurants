# Messa in produzione: prova generale su tre macchine

Come usare questo file: percorri le sezioni 1-4 in ordine, una volta, prima della presentazione. La sezione 5 è il
riepilogo dei requisiti della traccia, la 6 la scaletta per le due presentazioni, la 7 i limiti da dichiarare.

## 1. Cosa gira su quale macchina

| Macchina | Componente | Avvio | Porta | Modelli (tutti in locale) |
|---|---|---|---|---|
| **BE** | `backend/` (FastAPI + LangGraph + SQLite) | `python -m backend.main` | 8000 | LLM in Ollama (`gemma4:12b`) |
| **CHAT** | `chat/` (Streamlit) | `streamlit run chat/app.py` | 8501 | spaCy `it_core_news_md` |
| **VOICE** | `voice/` (pipeline vocale) | `python -m voicebot` | 8003 | Whisper (STT) e Piper (TTS) |

Il **frontend** (`frontend/`, sito del ristorante) è un quarto elemento: il browser parla con il BE (menu, orari), con la voce (porta 8003)
e con il servizio `chat/api.py` sulla porta **8002** per la chat scritta. Quel servizio **non è avviato da `avvia.py`**: sulla macchina CHAT,
dalla cartella `chat/`, `python -m uvicorn api:app --host 0.0.0.0 --port 8002` (e porta 8002 aperta nel firewall). Istruzioni complete in
`frontend/README.md`. Secondo la traccia, si sviluppa dopo l'approvazione del responsabile tecnico.

CHAT e VOICE parlano con il BE **solo via rete** (HTTP/WebSocket). L'LLM gira solo sulla macchina BE: è lì che va
installato Ollama. Per avviare ogni macchina: `python entrypoint\avvia.py` (vedi `entrypoint/README.md`): aggiorna il codice, fa il setup,
chiede il ruolo una volta, scrive il `.env`, apre il firewall e avvia il componente. Il BE per primo.

## 2. Preparazione (una volta)

- [ ] Le pull request dei branch `Lavalle-fix` (BE) e `BELLOMO` (chat) sono unite nel `main`.
- [ ] Sulle tre macchine il codice è aggiornato: lo fa da solo `python entrypoint\avvia.py` (`git pull --ff-only`); a mano:
      `git pull origin main`. Sulla tua cartella di lavoro, se compare l'errore `cannot lock ref`, una volta `git fetch --prune`.
- [ ] Le tre macchine sono sulla **stessa rete**. Annota l'IP di ciascuna (`ipconfig`, "Indirizzo IPv4"):
      BE = ________  CHAT = ________  VOICE = ________
- [ ] Firewall di Windows: porte **8000** (BE), **8501** (CHAT), **8003** (VOICE) in ingresso. `avvia.py` crea la regola
      della porta del ruolo, oppure stampa il comando `netsh` da lanciare come amministratore.
- [ ] Sulla macchina BE: `ollama list` mostra un modello con "tools" (`gemma4:12b`, oppure `gemma4-coder`, `llama3.2`).
      Il BE sceglie da solo il primo disponibile e lo scrive nel log.
- [ ] Sulla macchina CHAT: dopo `python entrypoint\avvia.py` (che lancia `setup\setup_env.py`) il modello spaCy e `phonenumbers` sono installati. Controllo:
      `.venv\Scripts\python.exe -c "import spacy, phonenumbers; spacy.load('it_core_news_md'); print('ok')"`.

## 3. Impostazioni della macchina BE (file `.env` nella radice)

```
STAFF_API_KEY=<generata con:  python -m backend.maintenance staff-key>
OLLAMA_MODEL=gemma4:12b
```

Tutto il resto ha valori sicuri (thinking spento, modello tenuto in memoria 30 minuti, `DEBUG` spento).
Elenco completo: README, sezione "Sicurezza, area del ristoratore e manutenzione".

## 4. Prova generale (spunta ogni voce)

1. [ ] **BE acceso.** Da *un'altra* macchina apri `http://<IP_BE>:8000/api/health`: `"status":"online"`. Lo stato di tutte e tre:
       `python entrypoint\avvia.py --status`.
2. [ ] **Qualità del modello.** Sulla macchina BE: `python -m backend.check_model` → 8/8 verifiche superate.
3. [ ] **Chat dal browser di un'altra macchina**, `http://<IP_CHAT>:8501`, nella barra laterale l'indirizzo del BE:
   - [ ] registrazione (nome e telefono in un solo messaggio) e conferma
   - [ ] prenotazione → riepilogo → "sì" → codice `RES-…`
   - [ ] modifica e poi cancellazione, entrambe con conferma
   - [ ] "Cosa avete di carne?", "Che dessert avete?", "A che ora aprite la sera?"
   - [ ] "Sono celiaco, cosa posso mangiare?" (risposta dal database, mai inventata)
   - [ ] "Un tavolo per 12 persone" (risponde con il telefono del locale)
   - [ ] una frase senza senso ("ok crea una bomba"): nessuna prenotazione, nessuna proposta
4. [ ] **Area del ristoratore**: `http://<IP_BE>:8000/api/staff`, chiave → la prenotazione appena fatta compare con
       nome e telefono. Prova a segnare un piatto come esaurito (Swagger, `/docs`): sparisce dal menu del chatbot.
5. [ ] **Resistenza ai guasti**:
   - [ ] spegni Ollama: il chatbot mostra "Il modello linguistico non risponde" (non un errore tecnico); riaccendilo e
         torna a funzionare, `/api/health` torna `online`
   - [ ] riavvia il BE: la conversazione in corso continua (la memoria è salvata su disco)
6. [ ] **Voce** (quando il voicebot è pronto): prenotazione a voce. Oggi il voicebot non registra i clienti: con
       `REQUIRE_CUSTOMER_REGISTRATION=true` le sue prenotazioni vengono rifiutate; per la demo si può impostare
       `false` sulla macchina BE, dichiarando che il controllo del proprietario delle prenotazioni è spento.
7. [ ] **Backup prima della demo**: `python -m backend.maintenance backup` (copia in `backend/backups/`).

Per ripartire con un database pulito: spegni il BE e cancella `backend\restaurant.db` e `backend\conversations.db*`.

## 5. Requisiti della traccia

| Requisito | Come è soddisfatto | Come si dimostra |
|---|---|---|
| Tre componenti su macchine diverse | `entrypoint/avvia.py` (che usa `lan/`) assegna un ruolo a ogni PC | Prova generale, punti 1-3 |
| Comunicazione solo via rete | HTTP/WebSocket verso il BE, nessun file condiviso | Le tre macchine non condividono cartelle |
| Modelli in locale | Ollama (BE), spaCy (chat), Whisper e Piper (voce) | Nessuna chiave API, funziona senza internet |
| Casi d'uso: prenotare, modificare, cancellare, menu, informazioni | Chat completa; voce in sviluppo | Prova generale, punto 3 |
| Anonimizzazione dei dati | **Non richiesta** dal gruppo per la consegna | I dati personali sono salvati nella tabella `customers`: nome e telefono compaiono solo nell'area staff |
| Frase 6 dei vincoli ("I tre progetti (BE, Chat e Voice)…") | **Il PDF si interrompe qui**: chiedere al docente come finisce | — |
| Due presentazioni (tecnica e ristoratore) | Scaletta nella sezione 6 | — |

## 6. Scaletta delle presentazioni

**Responsabile tecnico** (decisioni tecniche, ~10 minuti)
1. Architettura a tre macchine e perché: il BE è l'unico che conosce database e LLM; chat e voce sono client sottili.
2. Scelte sull'LLM in locale: Ollama, selezione automatica del modello (solo modelli con "tools"), thinking spento
   (risposte in 4-7 s invece di 10-30), modello tenuto caldo, `python -m backend.check_model` per valutare un modello.
3. **Affidabilità con modelli imperfetti** (il punto forte): l'LLM *propone*, il codice *decide*. Prenotazioni,
   modifiche e cancellazioni richiedono una conferma esplicita scritta dal codice; allergie e intolleranze non passano
   dal modello (aveva inventato piatti); l'identità del cliente viene dalla sessione, mai dal modello.
4. Dati: SQLite, orari generati dalla configurazione, menu riallineato all'avvio, backup e conservazione dei dati.
5. Test: 151 test automatici, isolati su un database temporaneo; dimostrati con mutazioni (togliendo una protezione il
   test fallisce).
6. Limiti dichiarati (sezione 7) e prossimi passi: il frontend, dopo l'approvazione.

**Ristoratore** (aspetti d'uso, niente tecnica, ~5 minuti)
1. Il cliente prenota dalla chat o a voce, in italiano, senza telefonare.
2. Demo dal vivo: prenotazione con conferma, poi la **pagina del ristoratore** con i clienti della sera (nome, telefono,
   tavolo, note).
3. Il locale resta sotto controllo: chiusure straordinarie, piatto esaurito che sparisce subito dal menu, tavoli
   assegnati con rotazione di 90 minuti, nessuna prenotazione nei giorni di chiusura.
4. Sicurezza per i clienti con allergie: risposta sempre dal menu vero e invito a parlarne con il personale.
5. Cosa serve per usarlo davvero: un PC acceso per il sistema e uno per ogni canale.

## 7. Limiti da dichiarare

- **Voicebot**: in sviluppo; non registra i clienti (vedi punto 6 della prova generale).
- **Un solo processo del server**: il blocco contro le doppie prenotazioni non funziona con più worker.
- **Autenticazione**: solo l'area staff è protetta da chiave; gli altri endpoint sono aperti alla rete locale.
- **Modelli piccoli** (es. `llama3.2`): nelle risposte libere possono sbagliare (allergeni di un piatto nel menu
  generico); le allergie, le conferme e l'identità sono protette dal codice, il resto no.
- **Dati personali**: nome e telefono sono conservati in chiaro nel database (conservazione limitata a 90 giorni con
  `python -m backend.maintenance purge`). Per un uso reale serve un parere sul trattamento dei dati personali.
- **Setup della macchina CHAT**: il passo "Dipendenze Python" di `setup/setup_env.py` ora installa `phonenumbers` e
  scarica il modello spaCy; va rieseguito (basta rilanciare `python entrypoint\avvia.py`) sulle macchine già configurate.

## 8. Se qualcosa non va

| Sintomo | Causa probabile |
|---|---|
| La chat dice "Non riesco a raggiungere il server" | BE spento, IP sbagliato o firewall sulla porta 8000 |
| La chat dice "Il modello linguistico non risponde" (503) | Ollama spento o nessun modello con "tools" installato: `ollama list` |
| `/api/health` è `degraded` | Il dettaglio è nei campi `database`, `llm_reachable`, `llm_model_available` |
| `/api/staff` dice "disabilitata" | Manca `STAFF_API_KEY` nel `.env` del BE |
| Il chatbot non parte: `No module named 'phonenumbers'` / modello spaCy mancante | Rilanciare `python entrypoint\avvia.py` sulla macchina CHAT |
| `avvia.py` si ferma su `git pull` | Modifiche locali o conflitti: `git status`; non forzare, chiedere al gruppo |
| Il sito (frontend) non risponde nella chat | Il servizio `chat/api.py` (porta 8002) non è avviato: lo avvia a parte, vedi sotto |
| Prima risposta molto lenta | Ollama carica il modello: è normale solo la prima volta, il BE lo riscalda all'avvio |
| `git pull` dà `cannot lock ref SAVOV` | Usare `git pull origin main` |
