# Presentazione tecnica — componente VOICE (AI 4 Restaurants)

> Guida passo per passo per presentare al project manager e ai senior. Si legge in ordine: ogni parte dice **cosa mostrare**,
> **cosa dire**, **perché abbiamo scelto così** e **dove guardare nel codice**. Le slide sono nei PDF della stessa cartella
> (`01`…`04`, più `00_presentazione_completa.pdf` con tutte le 48 slide, e la flowchart verticale `flowchart_flusso_codice.svg` / `05_flowchart_verticale.pdf`).
>
> Tempo stimato: 25–30 minuti + domande. Se ne hai 10: apertura, parte C (flusso), parte E (storia), chiusura.

---

## 0. Le tre frasi da ricordare

1. **Il Voice è «la chat con orecchie e bocca»**: stessa registrazione, stessa anonimizzazione, stessi endpoint del BE; cambia solo il trasporto (voce).
2. **Tutto gira in locale** (Ollama, Whisper, Piper): nessun dato personale esce dalla rete, e l'LLM non vede mai nome e telefono.
3. **Il BE decide, il Voice ascolta e parla**: il Voice decide solo *quando* chiedere i dati di contatto, come gestire il contesto e come far suonare bene le risposte.

**Numeri da sapere a memoria**

| Cosa | Valore |
|---|---|
| Commit / contributori / giorni | 90 · 3 · 3 (14–16 ottobre) |
| Test del voice | 192 (mypy strict su 29 file) |
| Porte | BE 8000 · CHAT 8501 (+ API sito 8002) · VOICE 8003 · sito vetrina 8080 |
| VAD | soglia 500, pausa 600 ms, voce minima 250 ms, segmento max 15 s |
| Barge-in | parlato ≥ 300 ms mentre il bot parla |
| Modello STT / TTS | Whisper `small` int8 su CPU · Piper `it_IT-riccardo-x_low` |
| Contesto | 20 scambi → nuova sessione; 3° giro avvisa; 4° giro chiude la chiamata |
| Popup di riepilogo | si chiude 4 s dopo il «sì» finale, solo a voce |
| Prestazioni misurate su portatile | primo turno di un cliente 41–75 s, poi 1–5 s |

---

## 1. Apertura (2 minuti) — slide `01` #2 «Il sistema in una pagina»

**Cosa mostrare:** lo schema delle tre macchine.

**Cosa dire**
- «Il progetto ha tre componenti su tre macchine nella stessa rete: **BE** (FastAPI + LangGraph + SQLite + Ollama), **CHAT** (Streamlit + API del sito) e **VOICE**, che è quello che presento.»
- «Il Voice riceve l'audio dal browser, lo trasforma in testo, parla col BE come farebbe la chat, e restituisce la risposta a voce.»
- «Il BE è l'unico che parla con l'LLM e col database: i client sono sottili.»

**Perché così:** vincolo di progetto: tre macchine separate, comunicazione di rete, modelli 100% locali.

**Dove guardare:** `docs/FLUSSO.md` (flussi), `lan/lan_config.json` (ruoli, porte, health).

---

## 2. Parte A — Ambiente: il venv (5 minuti) — `01_stack_tecnologico.pdf` #3–#4

**Problema che risolviamo:** tre persone, tre macchine, un solo repo. Un `requirements.txt` unico toccato da tutti generava conflitti di merge e installava cose inutili.

**Cosa dire**
1. «Abbiamo **un solo `.venv` alla radice**, ma i requisiti sono **per ruolo**: `base.txt` (sempre) + `be.txt` / `chat.txt` / `voice.txt` (+ `dev.txt` per i test).»
2. «Il setup salva in `.venv/.setup_state.json` l'**hash sha256** di ogni file di requisiti. Se un collega ne modifica uno, al prossimo avvio il setup se ne accorge e riparte da solo.»
3. «Il setup è in **sola libreria standard**: funziona anche con il venv rotto, perché è lui che lo ripara.»
4. «Installa **pacchetto per pacchetto** con output live. I pacchetti che richiedono un compilatore (es. `webrtcvad`) sono **opzionali**: se falliscono si va avanti, e il VAD a energia fa lo stesso lavoro.»
5. «Fa anche l'installazione *editable* (`pip install -e voice`), scarica la voce Piper (~28 MB), il modello spaCy (solo CHAT) e controlla Ollama (solo BE).»

**Dove guardare nel codice (`setup/setup_env.py`)**
- `plan_files(role, with_dev)` — riga 33: quali file di requisiti per quale ruolo.
- `step_requirements()` — riga 243: installazione e gestione degli opzionali.
- `is_setup(role)` — riga 394: il controllo veloce con gli hash.
- `setup/env_check.py`: l'hook `ensure_environment()` che ogni componente chiama all'avvio.

**Storia (da raccontare):** 7 modifiche a `setup_env.py` in 2 giorni; commit come «mio setup: tenere questa versione» e «fix setup env dopo merge sbagliato». La soluzione definitiva (`3fc4dbb`) è stata **un file per ruolo + hash**.

**Se ti chiedono «perché non Poetry/uv/Docker?»** → vincolo pratico: macchine Windows, demo in pochi giorni, nessuna installazione extra; il setup in stdlib parte da un Python qualsiasi. Docker per il voice esiste (`voice/Dockerfile`, multi-stage, non-root, healthcheck) ma **non è mai stato costruito** qui.

---

## 3. Parte B — LAN e avvio con un comando (4 minuti) — `01` #5–#6

**Problema:** ogni macchina deve sapere *chi è*, *dove sta il BE* e partire nell'ordine giusto.

**Cosa dire**
1. «Un solo comando per macchina: `python entrypoint\avvia.py`. Fa sette passi in ordine e si ferma con un messaggio chiaro al primo problema: **git pull (solo fast-forward) → identità → setup → .env → firewall → attesa del BE → avvio**.»
2. «L'**identità** (ruolo + IP, rilevato con un socket UDP che non invia nulla) si salva in `lan/macchina.json`, che non è in git.»
3. «Il `.env` si genera da `.env.example` con `BACKEND_BASE_URL=http://IP-BE:8000`.»
4. «CHAT e VOICE **non partono finché il BE non risponde** a `/api/health`: è il *cancello* sul BE.»
5. «Tutto è dichiarato in `lan/lan_config.json`: comando, cartella, porte, health, servizi extra (API del sito :8002, frontend :8080).»
6. «Per la demo: un Scheduled Task (`schtasks … /sc onlogon /delay 0000:30`) fa partire le macchine al login; il presentatore tocca **un solo PC** con `avvia.py --attendi`.»

**Dove guardare**
- `entrypoint/avvia.py` — `main()` riga 93 (i 7 passi).
- `lan/machine_setup.py` — `get_own_ip` (90), `configure_env` (235), `wait_for_be` (302), `cmd_autostart` (479).

**Storia:** `role.local.json` → `macchina.json` con IP rilevato (`5c0ad2b`), entrypoint (`96301d1`), identità (`3fc4dbb`), servizi extra (`81084e4`). Sette modifiche a `machine_setup.py` in due giorni.

**Onestà:** gli IP in `lan_config.json` sono **esempi**; la prova **a tre macchine dal vivo non è ancora stata fatta**.

### 3.1 L'entrypoint passo per passo (il tuo contributo — conoscilo bene)

Se qualcuno chiede «cosa succede quando lancio `avvia.py`?», segui questa tabella. Il codice è in `entrypoint/avvia.py` (`main`, riga 93) e in `lan/machine_setup.py`.

| # | Passo | Funzione | Se va storto |
|---|---|---|---|
| 1 | aggiorna il codice | `git_pull()` — `git pull --ff-only` | si ferma e stampa l'errore: mai merge automatici sporchi |
| 2 | identità | `resolve_role()` + `ensure_identity()` — ruolo (da `--role`, `LAN_ROLE`, `macchina.json` o domanda) e IP rilevato | lo chiede una volta sola |
| 3 | ambiente | `ensure_environment(role)` — confronta gli hash e installa solo se serve | si ferma e dice di rilanciare |
| 4 | `.env` | `configure_env()` — `BACKEND_BASE_URL`, `BE_URL`, `HOST`, e per il BE `OLLAMA_MODEL` | errore se manca `.env.example` |
| 5 | firewall | `firewall_hint()` — `netsh advfirewall … localport=<porta>` per ogni porta del ruolo | non blocca: stampa il comando da admin |
| 6 | cancello sul BE | `wait_for_be()` — `GET /api/health` ogni 2 s, max 180 s (solo CHAT e VOICE) | «BE assente»: il componente non parte |
| 7 | avvio | `start_component()` — processo principale + servizi extra, `Ctrl+C` li ferma tutti | — |

Varianti utili da citare: `--status` (tabella di stato), `--attendi` (il presentatore aspetta che tutte le macchine rispondano), `--sono` (identifica e basta), `--no-git --no-wait`, `--yes`.
**Dettaglio importante:** `--status` e `--attendi` usano gli IP di `lan_config.json`: con IP statici si fissano con `lan\machine_setup.py --pubblica-ip` e si condividono con git.
Flowchart verticale dell'intero flusso (avvio incluso): `docs/studio/voice/flowchart_flusso_codice.svg`. Tutti i comandi e le configurazioni di avvio (tre macchine, un PC, BE finto…): `MANUALE_TECNICO.md`, sezione 6.

---

## 4. Parte C — Il flusso del codice Voice (10 minuti) — `02_flusso_del_codice.pdf`

### 4.1 La mappa (slide #2)
Cinque livelli: **trasporto** (`pipeline/server.py`, `session.py`) → **audio** (`vad.py`, `stt.py`, `tts.py`, `audio.py`) → **conversazione** (`orchestrator.py`, `contacts.py`, `anonymizer.py`, `toolguard.py`, `prompts.py`, `spoken.py`) → **verso il BE** (`backend.py`) → **strumenti** (`doctor.py`, `local.py`, `devtools/stub_be.py`, `live_client.py`, `v2.py`).

### 4.2 Una chiamata, dall'orb al BE (slide #3) — il filo conduttore
Racconta questa sequenza, tenendola sullo schermo:

```
Browser --PCM 16 kHz--> Server WS --frame--> VAD --utterance--> STT --testo--> Orchestrator
Orchestrator: anonimizza -> POST /api/chat/stream (BE) -> token SSE -> ripristina + filtra
Orchestrator --frasi--> TTS (Piper) --audio PCM--> Server WS --audio + eventi--> Browser
```

- «Il browser manda audio PCM a 16 kHz in blocchi da 128 ms sul WebSocket `/ws/voice`.»
- «Il **VAD** capisce quando una persona ha finito: se la voce supera la soglia e poi c'è una pausa di 600 ms, produce una *utterance*.»
- «Lo **STT** (faster-whisper) la trasforma in testo.»
- «L'**orchestrator** anonimizza, chiama il BE, ripristina i segnaposto e passa le frasi al **TTS**, che parla appena la prima frase è pronta.»

**Dove guardare:** `pipeline/server.py` → `ws_voice` (riga 311) · `pipeline/session.py` → `_vad_loop` (175), `_stt_loop` (208), `_llm_loop` (235), `_speak` (285).

### 4.3 Le code e il barge-in (slide #4)
- «Tre fasi indipendenti collegate da `asyncio.Queue` **limitate**: se il server è in ritardo si perde il frame più vecchio, mai memoria che cresce (*backpressure*).»
- «**Barge-in**: se l'utente parla ≥ 300 ms mentre il bot parla, si annulla il turno, si svuota l'audio in coda e si avvisa il client.»
- «Un **contatore di generazione** (`_gen`) invalida il lavoro vecchio: ogni interruzione lo incrementa e i task scaduti si fermano da soli.»

**Dove guardare:** `session.py` → `_handle_barge_in` (343).

### 4.4 Il VAD (slide #5)
- Macchina a stati: silenzio → parlato in corso → utterance pronta. Parametri: soglia 500, pausa 600 ms, voce minima 250 ms, segmento max 15 s.
- **Il bug storico:** il tempo si contava sui *frame*; il browser ne manda da 128 ms e il client Python da 20 ms, quindi la pausa risultava **6 volte più lunga**. Ora il tempo è misurato sull'audio ricevuto.

**Dove guardare:** `vad.py` → `process_frame` (51).

### 4.5 STT e TTS (slide #6)
- STT: `small` int8 su CPU, `beam_size=1`, lingua da `.env`, `vad_filter=False` (il VAD è già nostro), scarta `no_speech_prob ≥ 0.6` e le «allucinazioni» note di Whisper; un lock = una trascrizione alla volta.
- TTS: i token diventano frasi (`SentenceChunker`) e Piper parla subito la prima; `speakable()` toglie markdown ed emoji e spiega i codici («R E S, 9 A 8 B…»); `spoken.py` dice numeri, date e orari a parole.

**Dove guardare:** `stt.py` → `transcribe` (78) · `tts.py` → `_SentenceTTS` (23) · `spoken.py` → `spoken_time` (81).

### 4.6 L'orchestrator: le fasi (slide #7)
1. **Benvenuto breve:** «Benvenuto alla Trattoria Bella Napoli! Come posso aiutarla?» — non si chiede niente.
2. **Fase CHAT:** menu e informazioni funzionano per tutti, col cliente anonimo condiviso `anon_voice`.
3. **Se si parla di prenotare** (`wants_booking`) parte la **REGISTRAZIONE**: nome e numero di telefono (il cognome è facoltativo), riepilogo, sì/no.
4. **`POST /api/customers`** → `customer_id` anonimo. L'LLM non vede mai i dati.
5. **Replay:** la richiesta originale («vorrei un tavolo per due alle 20») viene rimandata al BE, già anonimizzata, così il cliente non la ripete.
6. **Referto finale** a voce e **contesto**: dopo 20 scambi senza prenotazione, nuova sessione.

**Perché la registrazione «pigra»:** il saluto iniziale chiedeva troppo ed era poco amichevole; i dati servono solo per prenotare.

**Dove guardare:** `orchestrator.py` → `_local_turn` (259), `_registration_step` (402), `_rotate_if_full` (307) · `contacts.py` → `wants_booking` (207), `RegistrationDialog` (228), `extract_contacts` (151).

### 4.7 Privacy (slide #8)
| Dato | Dove va | Cosa vede l'LLM |
|---|---|---|
| Nome e telefono | solo `POST /api/customers` | niente (solo `cust_…`) |
| Frasi libere | `anonymize()` → `[NOME_1]`, `[TELEFONO_1]` | segnaposto |
| Risposta del BE | `restore()` prima della voce | — |
| Tutto ciò che esce | `scrub_pii()` (regex senza stato) | — |
| Log | telefono mascherato | — |

Strati dell'anonimizzatore: regex per forme fisse → regex per frasi che introducono un nome → spaCy (opzionale). **Segnaposto identici a quelli della CHAT** (il BE li riconosce).

**Dove guardare:** `anonymizer.py` → `Anonymizer` (72) · `pii.py` → `scrub_pii` (15).

### 4.8 Il filtro sulle risposte (slide #9)
- **Problema:** un modello piccolo a volte dice «Per vedere il menu devo prima chiamare get_menu. Vuole che verifichi?» o «Posso mostrarle i piatti…» invece di farlo.
- **Soluzione:** si trattiene la prima frase (≥ 40 caratteri), la si controlla (`leaks_tool_talk`), se è «sporca» si scarta e si riprova **una volta** con l'istruzione «usa subito gli strumenti, senza nominarli». Se fallisce ancora: «non sono riuscito a recuperare questa informazione, può ripetere?».
- **Test reale:** su una domanda sull'indirizzo la prima risposta era «Posso fornirti le informazioni generali…»; dopo il nuovo tentativo ha risposto con l'indirizzo vero in 5 s.

**Dove guardare:** `toolguard.py` → `leaks_tool_talk` (37) · `orchestrator.py` → `_backend_stream` (176).

### 4.9 Il referto finale (slide #10)
Dopo una prenotazione/modifica/cancellazione il bot **rilegge i dati veri** (`GET /api/reservations/{codice}`, solo il proprietario) e chiede un ultimo sì. Lo costruisce **il codice, non l'LLM**. «Sì» breve = fatto; **«sì, ma alle 21» non è un sì**: va al BE come modifica; «no» = si può cambiare.

**Dove guardare:** `orchestrator.py` → `_final_report` (350).

### 4.10 Contesto e prestazioni (slide #11)
- **Perché:** il BE tiene l'intero dialogo come contesto dell'LLM e, con un modello locale su CPU, più contesto = più lento.
- **20 scambi** senza arrivare a una prenotazione → nuova sessione BE e messaggio «sto gestendo molte richieste… ripartiamo da capo: una prenotazione o una modifica?». Il cliente **resta registrato**: nessuno ripete nome e telefono.
- **3° ripristino:** avvisa che potrebbe dover ricominciare. **4°:** chiude la chiamata (`call_ended`); si riparte premendo l'orb.
- **Warm-up** all'avvio (un turno finto al BE) e **id anonimo condiviso** `anon_voice`: stessa cache del prompt per tutti gli anonimi.

**Dove guardare:** `orchestrator.py` → `ANON_CUSTOMER_ID` (44), `_rotate_if_full` (307) · `pipeline/session.py` → `_finish_call` (260) · `pipeline/server.py` → `warm_backend` (98).

### 4.11 Protocollo WebSocket e sito (slide #12–#13)
- Su: PCM16 mono 16 kHz (binario) + `{"cmd":"eos"}` / `{"cmd":"reset"}`.
- Giù: PCM16 a 22.050 Hz (binario) + eventi JSON: `loading`, `ready`, `heard`, `transcript`, `thinking`, `reply`, `barge_in`, `registered`, `reservation`, `reservation_confirmed`, `call_ended`, `error`.
- Il sito (`/`) ha menu, info, «Le mie prenotazioni», il pulsante «Prenota a voce» che **diventa l'orb**, la chat «Scrivi» (spenta qui) e il **popup di riepilogo** (4 s dopo il «sì»). La pagina di test è `/test-voice`.
- L'orb si spiega da solo: pallini bianchi al centro = il BE pensa; anello dorato sottile e lento = riposo; si ispessisce = sta per parlare; ondeggia = parla.

### 4.12 Resilienza (slide #14)
Retry con backoff sul BE; **mai ritentare una richiesta non idempotente dopo un timeout** (niente prenotazioni doppie); riconnessione dello stream solo prima del primo token; errori tecnici mai letti a voce.

**Dove guardare:** `backend.py` → `_request` (77), `stream_chat` (199).

---

## 5. Parte D — Il BE e dove il Voice lo incontra (5 minuti) — `04_il_be_e_i_punti_di_contatto.pdf`

**Cosa dire**
1. «Il BE è FastAPI + LangGraph + SQLite + Ollama. Il Voice lo tocca in pochi punti, tutti in `voice/src/voicebot/backend.py`.»

| Nel Voice | Endpoint del BE | Cosa succede |
|---|---|---|
| `health_info()` | `GET /api/health` | online / degraded (DB e modello rispondono davvero) |
| `register_customer()` | `POST /api/customers` | salva nome+telefono, restituisce `cust_…` |
| `chat()` | `POST /api/chat` | un turno intero |
| `stream_chat()` | `POST /api/chat/stream` | il BE **prima** esegue il turno, **poi** manda le parole (30 ms l'una) |
| `get_reservation()` | `GET /api/reservations/{codice}?customer_id=` | solo il proprietario (altrimenti 404) |
| `/site/info`, `/site/menu` | `GET /api/info`, `GET /api/menu` | per il sito |

2. **Dentro un turno** (`backend/graph/workflow.py` → `process_message`, riga 228): (a) c'è una proposta in attesa e il cliente dice «sì» intero? → il **codice** esegue lo strumento; (b) è una domanda su allergie? → risposta **scritta dal codice** dal menu; (c) altrimenti entra l'LLM (`create_agent_node`, riga 134) con lo strumento giusto.
3. **Conferma esplicita:** per `create/modify/cancel_reservation` (`GATED_TOOLS`, riga 28) l'LLM può solo *proporre*; il BE risponde con un riepilogo scritto dal codice e agisce solo dopo un «sì» (`is_confirmation`, riga 66: solo parole di conferma, massimo 4). Nato da un bug reale: llama3.2 creava prenotazioni fantasma su saluti e frasi senza senso.
4. **Dati e regole** (`database/crud.py`): turni da **90 minuti** (`get_available_tables`, riga 192), tavolo più piccolo che basta, **lock** sull'allocazione (`table_lock`), pranzo 12:00–15:00 / cena 19:00–23:30, chiuso il lunedì, regole condivise in `validate_reservation_request` (riga 258).
5. **LLM provider** (`llm_provider.py`): sceglie il primo modello installato **che sa usare gli strumenti**, thinking spento di default, warm-up all'avvio, `keep_alive` 30 min.
6. **Sicurezza:** solo l'area staff ha una chiave (`X-API-Key` + `secrets.compare_digest`); il resto dell'API è aperto in LAN (CORS `*` di default). Il `customer_id` nei tool arriva **dalla sessione**, mai dal modello.

**Cose che il Voice ha scoperto sul BE (da dire con tatto, sono richieste, non accuse)**
- 🔴 **L'endpoint `/api/chat/stream` è `async` ma chiama `process_message` in modo bloccante** (`routes.py`, riga ~118): mentre l'LLM lavora, il BE non risponde a nulla, nemmeno a `/api/health`. L'ho osservato (timeout di 10–20 s).
- 🔴 **Il prompt mette data e `customer_id` in cima** (`prompts.py`, righe 20–50): ogni nuovo cliente e ogni nuovo giorno fa rileggere tutto al modello (su un portatile ~41–75 s la prima volta). Spostarli in fondo mantiene la cache.
- 🟠 Il modello a volte risponde con testo («Chiamo get_menu…») invece di usare lo strumento: il voice lo filtra, ma la causa è lato BE.
- 🟡 Il BE legge **solo l'ultimo messaggio** utente e usa il proprio prompt: il prompt vocale del voice (`voice/src/voicebot/prompts.py`) è per ora una *specifica*.
- 🟡 Nessun endpoint «prenotazioni di questo cliente»: la pagina ricorda i codici nel browser.

---

## 6. Parte E — Storia: problemi ricorrenti e come li abbiamo risolti (6 minuti) — `03_storia_fix_e_decisioni.pdf`

**Messaggio:** *sette problemi, cinque cause; ogni decisione di progetto nasce da un incidente reale.* (slide #12)

| # | Problema ricorrente | Decisione | Evidenza (git) |
|---|---|---|---|
| 1 | Setup del venv e conflitti di merge | requisiti per ruolo + hash, setup in stdlib | `b8c1712` → `1aa2df6` → `1c172bd` → `58e1f38` → `5af2bf3` → `3fc4dbb` |
| 2 | Ruoli, IP e ordine di avvio sulle 3 macchine | `macchina.json`, `avvia.py`, cancello sul BE | `5c0ad2b`, `96301d1`, `3fc4dbb`, `81084e4` |
| 3 | Pipeline vocale col modello vero | VAD sul tempo reale, modelli condivisi/precaricati, mai ritentare POST, test ermetici | `cd1be40` |
| 4 | Il parlato non è testo | Whisper `small`, prompt spento, cifre unite, numeri a parole | `f073570`, `d18d33c` |
| 5 | I modelli piccoli sbagliano | **l'LLM propone, il codice decide**: conferma, allergie da codice, filtro | `06d45e1`, `3baf68c`, `c7c1599`, `toolguard.py` |
| 6 | La privacy decide l'architettura | `customer_id` anonimo, un solo endpoint con dati, anonimizzatore condiviso | `6f64a50`, `b909025` |
| 7 | Docs e configurazione si disallineano | test sui docs, ripristino della pagina originale | `55069b6`, `27b67cc` |

**Come raccontarli (formula: sintomo → causa → fix → lezione)**
- **#1:** «Sembrava un problema di venv, era un problema di *file condiviso*. La lezione: un file per persona/ruolo.»
- **#3:** «Il VAD sembrava rotto: la pausa era 6 volte più lunga. Il browser manda blocchi da 128 ms, il client da 20: contavamo frame, non tempo.»
- **#5:** «Non fidarsi mai dell'LLM per ciò che ha conseguenze: prenotazioni e allergie le decide il codice.»
- **#7:** «Abbiamo riscritto una pagina di test perdendo le animazioni: abbiamo ripristinato l'originale. Lezione: estendere, non riscrivere.»

**Gli ultimi giorni (slide #11):** saluto breve + registrazione pigra; prompt in italiano; popup; contesto e warm-up; filtro sulle risposte; anello dorato; pulsante→orb; `/test-voice`.

---

## 7. Chiusura (2 minuti) — `03` #13 «Cosa resta aperto»

**Risultati:** un voicebot che si comporta come la chat, locale, con privacy per costruzione, 192 test, strumenti di diagnosi (`doctor`, `/diag`), e un sito con orb, popup e chat.

**Rischi e limiti da dichiarare (meglio dirli tu che farteli scoprire):**
- La prova **a tre macchine dal vivo non è stata ancora fatta**.
- Una sola trascrizione alla volta (lock sul modello condiviso) e un solo LLM: **più chiamate in parallelo si mettono in coda**.
- Il riconoscimento è legato alla lingua dell'`.env`: altre lingue non sono trascritte bene anche se il prompt le capisce.
- Il browser concede il microfono solo su `localhost` o HTTPS: da un altro PC in HTTP serve `python -m voicebot live ws://HOST:8003/ws/voice`.
- Il `Dockerfile` non è mai stato costruito. CORS aperto di default in LAN. Nessuna autenticazione sull'API del BE (tranne l'area staff).
- Prestazioni su CPU debole: dipendono da macchina e modello (vedi i numeri sopra).

**Prossimi passi:** i cinque punti della slide `04` #10 (prompt del BE, endpoint async, testo al posto degli strumenti, `num_ctx`, cognome solo se serve).

---

## 8. Domande difficili (preparate)

**«Perché tutto in locale? Un'API cloud sarebbe più veloce e accurata.»**
Vincolo di progetto e di privacy: nome e telefono non devono uscire dalla rete. Con modelli locali il costo è la velocità: lo abbiamo misurato e mitigato (warm-up, contesto limitato, cache).

**«L'LLM può vedere dati personali?»**
No. Nome e telefono vanno solo a `POST /api/customers`; il resto passa dall'anonimizzatore (segnaposto) e da `scrub_pii`. Nei tool il `customer_id` viene dalla sessione, non dal modello.

**«E se il BE è spento o lento?»**
Il Voice aspetta il BE all'avvio (cancello), ritenta con backoff le richieste sicure, **non ritenta** quelle non idempotenti dopo un timeout, e al cliente dice una frase gentile, mai un errore tecnico.

**«Quante chiamate in parallelo reggete?»**
Onestamente: poche. Il modello STT è condiviso con un lock e c'è un solo LLM. Va misurato su macchine più potenti; è tra i prossimi passi.

**«Come sapete che funziona?»**
192 test (di cui molti end-to-end contro un BE finto che imita registrazione e conferma), mypy strict, `doctor` con 12 controlli e una prova reale col modello e con Whisper/Piper veri. **Non** abbiamo ancora fatto la prova a tre macchine.

**«Perché Whisper `small` e non `tiny`?»**
`tiny` sbaglia numeri e nomi, e per prenotare servono data, ora, persone e telefono. `small` è il compromesso: ~1,5 s ogni 4 s di parlato su una CPU libera (dato dell'`.env.example`); sul portatile di sviluppo, con l'LLM acceso, abbiamo misurato 3–4 s per frase.

**«Perché un VAD a energia invece di uno più sofisticato?»**
Zero dipendenze compilate su Windows e comportamento prevedibile. Esiste `webrtcvad` come opzione.

**«Perché il Voice non usa direttamente il servizio CHAT?»**
La traccia dice che CHAT e VOICE parlano solo col BE. C'è comunque una modalità opzionale (`CHAT_SERVICE_URL`) per appoggiarsi alla CHAT.

**«Come gestite i modelli che sbagliano?»**
Tre livelli: il BE fa decidere al codice ciò che ha conseguenze (conferma, allergie); il Voice scarta le risposte che parlano di strumenti e ritenta una volta; poi una frase neutra.

**«Cosa succede ai dati dopo?»**
Nome e telefono restano nella tabella `customers`; `python -m backend.maintenance purge` li cancella dopo N giorni (90 di default).

**«Quanto è sicuro?»**
L'area staff richiede `X-API-Key`; solo il proprietario legge/modifica/cancella una prenotazione (404 per gli altri). Limiti: API del BE aperta in LAN, CORS `*`. In produzione andrebbero messi un reverse proxy e HTTPS.

**«Cosa rifareste diversamente?»**
Il prompt del BE con le parti per cliente in fondo dall'inizio; un file di requisiti per ruolo dal primo giorno; test sui docs prima che i docs divergessero.

---

## 9. Demo (se richiesta) — comandi e cosa mostrare

| Cosa | Comando / indirizzo | Cosa far notare |
|---|---|---|
| Diagnosi | `python -m voicebot doctor` | 12 controlli con rimedio per ognuno |
| Test del voice | `cd voice` · `python -m pytest tests -q` · `python -m mypy src` | 192 passati, mypy pulito |
| Prova locale completa | `voice\voice local` (BE finto + server + browser) | banner «LOCAL TEST» |
| Con il BE vero | `python -m voicebot` → `http://localhost:8003/` | orb, popup, «Le mie prenotazioni» |
| Pagina tecnica | `http://localhost:8003/test-voice` | tab TECNICA/STATO, trascrizione, eventi |
| Stato LAN | `python entrypoint\avvia.py --status` | le tre macchine e i loro health |

Frase d'esempio per la demo: *«Vorrei prenotare un tavolo per due domani alle venti»* → il bot chiede nome e telefono → riepilogo → conferma → riepilogo finale → popup con nome, data, ora, persone → «sì» → il popup sparisce dopo 4 secondi.

---

## 10. Glossario

| Termine | Significato |
|---|---|
| **VAD** | Voice Activity Detection: capisce quando c'è voce e quando la frase è finita |
| **STT / TTS** | Speech-to-Text (Whisper) / Text-to-Speech (Piper) |
| **Barge-in** | L'utente interrompe il bot mentre parla |
| **Backpressure** | Code con dimensione massima: si scarta il vecchio invece di far crescere la memoria |
| **SSE** | Server-Sent Events: il server manda dati a pezzi su una risposta HTTP |
| **Prompt cache** | L'LLM riusa l'inizio identico del prompt senza rileggerlo |
| **Cancello sul BE** | I client aspettano `/api/health` prima di partire |
| **Segnaposto** | `[NOME_1]`, `[TELEFONO_1]`: al posto dei dati personali verso l'LLM |
| **E.164** | Formato internazionale del telefono (`+393331234567`) |
| **Checkpointer** | Memoria delle conversazioni del BE (SQLite, per `session_id`) |
| **Idempotente** | Ripetere la richiesta non cambia il risultato (GET sì, POST no) |
| **Gated tool** | Strumento che modifica dati e richiede conferma del cliente |

---

## 11. Mappa rapida dei file (dove guardare, in ordine di importanza)

| File | Responsabilità |
|---|---|
| `voice/src/voicebot/orchestrator.py` | Il cervello: fasi, registrazione pigra, filtro, referto, contesto |
| `voice/src/voicebot/pipeline/session.py` | Le tre fasi con code, barge-in, fine chiamata |
| `voice/src/voicebot/pipeline/server.py` | FastAPI: WebSocket, sito, proxy `/site/*`, warm-up |
| `voice/src/voicebot/contacts.py` | Dialogo di registrazione e `wants_booking` |
| `voice/src/voicebot/anonymizer.py`, `pii.py` | Privacy |
| `voice/src/voicebot/toolguard.py` | Filtro sulle risposte |
| `voice/src/voicebot/backend.py` | Client HTTP del BE con retry |
| `voice/src/voicebot/vad.py`, `stt.py`, `tts.py` | Audio locale |
| `voice/src/voicebot/prompts.py`, `messages.py`, `spoken.py` | Prompt e frasi dette a voce |
| `voice/src/voicebot/doctor.py`, `diagnostics.py` | «Perché non funziona?» |
| `voice/src/voicebot/devtools/stub_be.py` | BE finto per i test |
| `voice/src/voicebot/pipeline/site/` | Sito: orb, popup, chat, «Le mie prenotazioni» |
| `setup/setup_env.py` | Il venv, i requisiti per ruolo, i modelli |
| `entrypoint/avvia.py`, `lan/machine_setup.py` | Avvio a un comando e rete |
| `backend/graph/workflow.py` | Il turno del BE: conferma, allergie, agente |
| `backend/database/crud.py` | Regole di business e tavoli |

---

*Sorgenti delle slide: `docs/studio/voice/_sorgenti/` — per rigenerare i PDF: `python docs/studio/voice/_sorgenti/build.py` (serve solo Edge o Chrome).*
