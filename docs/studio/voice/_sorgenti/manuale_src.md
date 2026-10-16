# Manuale tecnico — AI 4 Restaurants

**Componenti:** BE · CHAT · VOICE · entrypoint · LAN · setup  
**Per chi è:** colleghi che devono installare, avviare, testare e presentare il sistema  
**Piattaforma:** Windows 10/11, terminale `cmd` o PowerShell, percorsi dalla radice del repo (`AI_4_Restaurants\`)  
**Aggiornato:** 16 ottobre 2026 · verificato sul codice del branch `casa_savov`

> **Come si legge.** Le sezioni 1–5 sono il manuale di consultazione (installare, comandi per componente, test, sessioni live).
> La sezione **6** è quella da seguire il giorno della prova: spiega **come far partire le varie configurazioni**, a cominciare
> da quella **principale richiesta dalla traccia: tre macchine separate in rete (BE, CHAT, VOICE)**.
> I riquadri **Nota** e **Attenzione** raccolgono le trappole già incontrate.

{{TOC}}

---

## 1. Convenzioni e prerequisiti

### 1.1 Convenzioni

| Simbolo | Significato |
|---|---|
| `comando` | da scrivere nel terminale, dalla **radice del repo** salvo diversa indicazione |
| `<IP_BE>` | indirizzo IPv4 della macchina BE (es. `192.168.1.10`): lo trovi con `ipconfig` → «Indirizzo IPv4» |
| **BE / CHAT / VOICE** | i tre componenti: backend (LLM + database), chatbot testuale, voicebot |
| **Presentatore** | la persona che durante la demo tocca un solo PC |

> **Nota.** In tutto il manuale `python` è l'interprete che hai nel `PATH`. Dopo il setup puoi usare
> `.venv\Scripts\python` ovunque, che è sempre quello giusto.

### 1.2 Cosa serve su ogni macchina

| Requisito | BE | CHAT | VOICE | Note |
|---|:-:|:-:|:-:|---|
| Windows 10/11 | ✔ | ✔ | ✔ | gli script sono pensati per Windows |
| Python ≥ 3.10 (meglio 3.11/3.12) | ✔ | ✔ | ✔ | il setup lo controlla |
| git | ✔ | ✔ | ✔ | per `git pull --ff-only` |
| Rete locale condivisa | ✔ | ✔ | ✔ | stessa LAN/Wi-Fi, IP stabili o DHCP riservati |
| Ollama + modello con strumenti | ✔ | | | `gemma4:12b` (o un ripiego: vedi 3.7) |
| Microfono e casse | | | ✔ | per la prova a voce |
| Edge o Chrome | | | | solo per rigenerare le slide |

> **Attenzione.** Il browser concede il microfono solo su pagine «sicure»: `http://localhost…` va bene,
> `http://192.168.x.x…` **no**. Per parlare, apri il sito del Voice **sul PC VOICE** (`http://localhost:8003/`)
> oppure usa il client live (sezione 6.5).

### 1.3 Porte e indirizzi

| Servizio | Porta | Health | Dove |
|---|---|---|---|
| BE (FastAPI) | 8000 | `/api/health` | macchina BE · Swagger su `/docs` |
| Sito vetrina (`frontend/`) | 8080 | `/` | macchina BE (servito con `http.server`); sulla CHAT parte da solo |
| **Gateway** (sito completo, reverse proxy) | 8090 (https) | `/health` | macchina BE · `showcase/gateway.py` · gli altri PC aprono `https://<IP-BE>:8090/` |
| CHAT Streamlit | 8501 | `/_stcore/health` | macchina CHAT |
| API CHAT per il sito | 8002 | `/health` | macchina CHAT |
| VOICE (sito + WebSocket) | 8003 | `/health` | macchina VOICE · WS `/ws/voice` · test `/test-voice` |

Firewall: apri **8000, 8080, 8090 (BE), 8501, 8002 (CHAT), 8003 (VOICE) TCP in ingresso** (l'entrypoint prova da solo; altrimenti stampa il comando `netsh` da lanciare come amministratore).

---

## 2. Installazione e configurazione

### 2.1 Clonare il repo

```bat
git clone https://github.com/KsandarIV/AI_4_Restaurants.git
cd AI_4_Restaurants
```

### 2.2 Il metodo consigliato: l'entrypoint

```bat
python entrypoint\avvia.py
```

Alla **prima volta** su una macchina fa tutto da solo e ti fa **due domande**: *ruolo* (be/chat/voice) e *IP del BE*.
Le risposte vengono ricordate (`lan\macchina.json` e `.env`): dalla seconda volta non chiede più niente. Dettaglio dei passi nella sezione 3.1.

### 2.3 Solo l'ambiente (venv + modelli)

```bat
python setup\setup_env.py --role voice --with-dev     :: venv per il voice + strumenti di test
python setup\setup_env.py --role be                   :: venv per il BE
python setup\setup_env.py --role chat                 :: venv per la CHAT (include spaCy)
python setup\setup_env.py --role all --yes            :: tutto, senza domande (sviluppo su un solo PC)
python setup\setup_env.py --check-only                :: verifica veloce, esce con 0 (ok) o 1
```

| Opzione | Effetto |
|---|---|
| `--role be\|chat\|voice\|all` | installa `base` + il ruolo (default `all`) |
| `--with-dev` | aggiunge `dev.txt` (pytest, pytest-asyncio, mypy) anche con un ruolo singolo |
| `--yes` / `-y` | accetta ogni passo e ogni download |
| `--check-only` | non installa nulla: controlla gli hash dei requisiti |
| `--skip-requirements` `--skip-ollama` `--skip-piper` | salta il singolo passo |

Cosa fa, in ordine: controlla Python → crea `.venv` → installa i pacchetti **uno per uno** (output live; quelli *opzionali* come `webrtcvad` possono fallire) → installazione *editable* di `voice/` → modello spaCy `it_core_news_md` (solo CHAT) → controlla Ollama e scarica il modello (solo BE) → scarica la voce Piper (~28 MB) in `voice\models\` → scrive `.venv\.setup_state.json` con l'hash dei file di requisiti.

> **Nota.** Se un collega cambia un file in `setup\requirements\`, al prossimo avvio il setup se ne accorge e riparte da solo.
> `VOICE_SETUP_SKIP=1` salta il controllo (solo per emergenze).

### 2.4 Il file `.env`

Un unico `.env` alla radice (mai in git). Lo genera `avvia.py` partendo da `.env.example`; per farlo a mano:

```bat
copy .env.example .env
```

**Variabili più usate**

| Componente | Variabile | Significato | Default / esempio |
|---|---|---|---|
| tutti | `BACKEND_BASE_URL` | indirizzo del BE (**non** `localhost` se il BE è su un altro PC) | `http://192.168.1.10:8000` |
| BE | `OLLAMA_MODEL` | modello (anche elenco in ordine di preferenza) | `gemma4:12b` |
| BE | `OLLAMA_FALLBACK_MODELS` | ripieghi | `gemma4-coder,llama3.2` |
| BE | `OLLAMA_TIMEOUT_S` · `OLLAMA_KEEP_ALIVE` | attesa massima · permanenza in memoria | `120` · `30m` |
| BE | `STAFF_API_KEY` | chiave dell'area staff (vuota = disabilitata) | generata con `staff-key` |
| BE | `REQUIRE_CUSTOMER_REGISTRATION` | prenotare solo da clienti registrati | `true` |
| BE | `CLOSED_WEEKDAYS` · `DATA_RETENTION_DAYS` | giorni di chiusura (0 = lunedì) · giorni di conservazione dati | `0` · `90` |
| BE | `CORS_ORIGINS` · `DEBUG` · `HOST` · `PORT` | rete e debug | `*` · `false` · `0.0.0.0` · `8000` |
| VOICE | `VOICE_HOST` · `VOICE_PORT` | dove ascolta | `0.0.0.0` · `8003` |
| VOICE | `VOICE_LANGUAGE` | lingua delle frasi del bot e di Whisper | `it` |
| VOICE | `STT_MODEL` · `STT_DEVICE` · `STT_COMPUTE_TYPE` | Whisper | `small` · `cpu` · `int8` |
| VOICE | `VAD_ENERGY_THRESHOLD` · `VAD_SILENCE_MS` | soglia voce · pausa che chiude la frase | `900` · `600` |
| VOICE | `VAD_MIN_SPEECH_MS` · `BARGE_IN_MIN_MS` | durata minima di una frase per arrivare al riconoscimento · durata minima per interrompere il bot (anti colpi e tosse) | `450` · `700` |
| VOICE | `REQUIRE_REGISTRATION` | specchio del BE: chiedere nome e telefono | `true` |
| VOICE | `CONTEXT_MAX_EXCHANGES` · `CONTEXT_MAX_RESETS` | scambi prima di una nuova sessione · ripristini prima di chiudere | `20` · `3` |
| VOICE | `WARM_BACKEND` · `PRELOAD_MODELS` | turno di riscaldamento al BE · carica i modelli all'avvio | `true` · `true` |
| VOICE | `CHAT_SERVICE_URL` | se impostata, chat del sito e modalità v2 passano dal servizio CHAT | vuota |
| VOICE | `LOG_LEVEL` | verbosità dei log | `INFO` |

> **Attenzione.** Il `.env` è **della macchina**: contiene l'IP del BE. Non copiarlo da un PC all'altro.

---

## 3. Comandi per componente

### 3.1 Entrypoint — `entrypoint\avvia.py`

Un solo comando per macchina; fa **sette passi in ordine** e si ferma con un messaggio chiaro al primo problema.

| # | Passo | Cosa fa | Se qualcosa va storto |
|---|---|---|---|
| 1 | `git pull --ff-only` | aggiorna il codice (mai merge sporchi) | si ferma: «`git status`, non forzare, chiedi al gruppo» |
| 2 | Identità | ruolo + IP rilevato (socket UDP, nessun pacchetto inviato) → `lan\macchina.json` | se non c'è il ruolo lo chiede una volta |
| 3 | Setup per ruolo | `ensure_environment(role)`: installa solo se gli hash non coincidono | si ferma e dice di rilanciare |
| 4 | `.env` | scrive `BACKEND_BASE_URL=http://<IP_BE>:8000` (IP chiesto una volta) | errore se manca `.env.example` |
| 5 | Firewall | prova `netsh advfirewall … localport=<porta>` per ogni porta del ruolo | non blocca: stampa il comando da admin |
| 6 | Cancello sul BE | **solo CHAT e VOICE**: attende `GET /api/health` ogni 2 s, fino a 180 s | se scade: «BE assente, componente NON avviato» (`--no-wait` per saltare) |
| 7 | Avvio | lancia il componente in primo piano (più i servizi extra) con log live | `Ctrl+C` ferma tutto |

```bat
python entrypoint\avvia.py                          :: prima volta o aggiornamento
python entrypoint\avvia.py --role voice             :: forza il ruolo
python entrypoint\avvia.py --be-host 192.168.1.10   :: imposta l'IP del BE
python entrypoint\avvia.py --yes                    :: risponde sì a tutto nel setup
python entrypoint\avvia.py --no-git --no-wait       :: salta l'aggiornamento e l'attesa del BE
python entrypoint\avvia.py --status                 :: stato HTTP delle tre macchine
python entrypoint\avvia.py --attendi                :: PRESENTATORE: aspetta che tutte rispondano (max 600 s)
python entrypoint\avvia.py --attendi --attendi-timeout 900
python entrypoint\avvia.py --sono --role be         :: identifica la macchina e basta
```

> **Nota.** `--status` e `--attendi` controllano gli altri PC con gli IP di `lan\lan_config.json`.
> Quegli IP sono **esempi** finché non li fissi: vedi 6.1, passo «Pubblica gli IP».

### 3.2 LAN — `lan\machine_setup.py`

Lo stesso script dell'entrypoint, ma **senza** `git pull` e setup (uso diretto, codice già aggiornato).

```bat
python lan\machine_setup.py                         :: primo giro: ruolo, setup, .env, firewall, avvio
python lan\machine_setup.py --role voice --start    :: avvio diretto
python lan\machine_setup.py --sono --role voice     :: identifica e basta
python lan\machine_setup.py --mostra-identita       :: chi sono io e chi sono gli altri
python lan\machine_setup.py --status                :: ping HTTP a be/chat/voice
python lan\machine_setup.py --be-host 192.168.1.10 --configure-only   :: solo .env
python lan\machine_setup.py --pubblica-ip           :: scrive il mio IP in lan_config.json (solo IP statici)
python lan\machine_setup.py --write-launcher        :: crea AVVIA_<RUOLO>.bat (doppio clic)
python lan\machine_setup.py --installa-avvio        :: avvio automatico al login (+30 s), una tantum
python lan\machine_setup.py --rimuovi-avvio         :: toglie l'avvio automatico
python lan\machine_setup.py --role chat --no-wait --wait-timeout 60
set LAN_ROLE=be && python lan\machine_setup.py      :: ruolo da variabile (laboratorio)
```

`lan\lan_config.json` descrive ogni ruolo (cartella, porta, health, comando di avvio, servizi **extra**) e l'ordine di avvio `be → chat → voice`.

### 3.3 BE

```bat
python -m backend.main                               :: avvio (porta 8000)
python -m backend.check_model                        :: 8 prove sul modello scelto, con OK/KO e tempi
python -m backend.maintenance backup                 :: copia consistente del database (ultimi 14)
python -m backend.maintenance purge --dry-run        :: quanti clienti verrebbero cancellati
python -m backend.maintenance purge                  :: cancella nome e telefono oltre DATA_RETENTION_DAYS
python -m backend.maintenance staff-key              :: genera una chiave per l'area staff
```

| Cosa | Dove |
|---|---|
| Documentazione interattiva | `http://<IP_BE>:8000/docs` |
| Stato (DB + modello) | `http://<IP_BE>:8000/api/health` → `online` / `degraded` |
| Area del ristoratore | `http://<IP_BE>:8000/api/staff` (serve `STAFF_API_KEY` nell'intestazione `X-API-Key`) |

Per ripartire con un database pulito: spegni il BE e cancella `backend\restaurant.db` e `backend\conversations.db*`.

> **Attenzione.** Il BE non risponde ad altre richieste mentre l'LLM sta elaborando un turno di streaming
> (anche `/api/health` resta fermo). È un limite noto: vedi sezione 7.

### 3.4 CHAT

```bat
streamlit run chat\app.py                            :: chatbot Streamlit (porta 8501)
cd chat && python -m uvicorn api:app --host 0.0.0.0 --port 8002   :: API per il sito (porta 8002)
```

`avvia.py` con ruolo `chat` avvia **entrambi** nello stesso terminale (il secondo è un servizio *extra*). La CHAT non parla mai al BE dal browser: passa da `chat/api.py`.

### 3.5 VOICE

Un solo punto d'ingresso: `voice\voice.bat <comando>` (equivale a `python -m voicebot <comando>`).

| Comando | Cosa fa | Quando |
|---|---|---|
| `voice\voice serve` | avvia il server (sito + WebSocket) | uso normale |
| `voice\voice real [--wait 60]` | controlla il BE (lo aspetta) e poi avvia | flusso vero, componente singolo |
| `voice\voice local [--fake] [--port N] [--no-browser]` | **BE finto** + server + browser, un comando | prova senza altro |
| `voice\voice doctor [--be-url URL] [--json] [--load-models]` | «perché non funziona?» | sempre, prima di chiamare qualcuno |
| `voice\voice v2 [--text] [--no-speaker] [--verbose]` | chat vocale «una domanda, una risposta» da questo PC | senza browser |
| `voice\voice live [ws://HOST:8003/ws/voice] [--half-duplex]` | chiamata live da questo PC (microfono e casse locali) | microfono da un altro PC |
| `voice\voice test` | esegue i test del voice | sviluppo |

| Indirizzo (sul PC VOICE) | Cosa mostra |
|---|---|
| `http://localhost:8003/` | il sito: menu, info, «Le mie prenotazioni», pulsante **Prenota a voce** (diventa l'orb), chat **Scrivi** |
| `http://localhost:8003/test-voice` | pagina di test: orb, tab TECNICA / STATO, trascrizione ed eventi, banner con il BE in uso |
| `…/health` · `…/ready` · `…/diag` | stato del server, modelli pronti, report completo |
| `…/tech` · `…/tech-codice` · `…/tech-idea` | pagine tecniche di spiegazione |

> **Nota.** `voice\voice` senza argomenti mostra solo l'aiuto; `python -m voicebot` senza argomenti, invece, avvia il server.
> `/prova-vocale` e `/prova-vocale-test` (vecchi indirizzi) reindirizzano a `/test-voice`.

### 3.6 Sito vetrina (frontend)

```bat
python -m http.server 8080 --directory frontend      :: avvio manuale; con avvia.py (ruolo be) parte da solo
```

Aprire `http://localhost:8080` **sul PC che lo ospita** (per il microfono). Gli indirizzi dei tre componenti sono in `frontend\js\config.js` (**unico** punto da modificare).

**Sito completo (chat + voce + area ristoratore).** Sul BE `avvia.py` avvia anche il **gateway** (`showcase/gateway.py`, https :8090): un reverse proxy che serve il sito e inoltra `/api/*` al BE, `/voice/*` (WebSocket compreso) al PC VOICE e la finestrella chat al PC CHAT, così **CHAT e VOICE non si parlano mai tra loro**. Si apre su `https://completo.localhost:8090/` (BE) e `https://<IP-BE>:8090/` (CHAT e VOICE; certificato autofirmato: «Avanzate → Procedi» una volta). CHAT e VOICE si annunciano al gateway (`POST /register`); gli indirizzi non si scrivono a mano: `python -m showcase.peers show`. Dettagli: [showcase/README.md](../showcase/README.md), elenco dei siti: [SITI.md](SITI.md).

### 3.7 Ollama e modelli

```bat
ollama serve                                         :: se l'app non è già in esecuzione
ollama list                                          :: modelli installati
ollama pull gemma4:12b                               :: modello consigliato per il BE
ollama create gemma4-voice -f voice\local_llm\Modelfile   :: copia leggera per PC deboli (contesto 8k)
ollama ps                                            :: modello in memoria e uso di CPU/GPU
```

Il BE sceglie da solo il **primo modello installato che sa usare gli strumenti** (`OLLAMA_MODEL`, poi i ripieghi) e lo scrive nel log e in `/api/health`.

---

## 4. Test

### 4.1 Test automatici

| Cosa | Comando | Risultato atteso |
|---|---|---|
| **Voice** (225+ test) | `voice\voice test` oppure `cd voice` + `python -m pytest tests -q` | `225 passed` o più |
| Voice, un file | `cd voice` + `python -m pytest tests\test_orchestrator.py -q` | |
| Tipi (mypy strict) | `cd voice` + `python -m mypy src` | `Success: no issues found` |
| **BE** | `python -m pytest tests -q` (dalla radice) | tutti verdi |
| Modello del BE | `python -m backend.check_model` | 8/8 prove superate |
| **CHAT** (prove manuali) | `python chat\test_anonimizzatore.py` · `python chat\test_contatti.py` · `python chat\test_rompi_chatbot.py` | nessun KO |

> **Attenzione.** Per il BE scrivi sempre `tests`: senza, pytest raccoglie anche `voice\` e va in errore se il pacchetto `voicebot` non è installato.

**Cosa coprono i test del voice**

| File | Argomento |
|---|---|
| `test_orchestrator` · `test_context` · `test_anon` | fasi, registrazione pigra, 20 scambi e chiusura, id anonimo condiviso |
| `test_contacts` · `test_anonymizer` · `test_units` | dialogo di registrazione, privacy, VAD/audio/spoken |
| `test_toolguard` | filtro sulle risposte che parlano di strumenti |
| `test_report` | referto finale a voce e popup |
| `test_pipeline` · `test_server` | pipeline con code, WebSocket vero, chiamata end-to-end |
| `test_site` · `test_docs` | sito (orb, popup, chat, `/test-voice`), docs coerenti con il codice |
| `test_backend` · `test_doctor` · `test_v2` | client del BE, diagnosi, modalità v2 |

I test usano un **BE finto** (`voicebot/devtools/stub_be.py`) che imita registrazione, conferma sì/no, modifica e cancellazione: non serve nient'altro acceso.

### 4.2 Test manuali (checklist)

**Prima di ogni prova**

1. `python -m voicebot doctor` → tutti `OK` (a parte il BE se non è ancora acceso).
2. `python entrypoint\avvia.py --status` → `TUTTO OK`.
3. `http://<IP_BE>:8000/api/health` → `"status":"online"`.

**Prova a voce (sul PC VOICE, `http://localhost:8003/`)**

| # | Cosa dire / fare | Atteso |
|---|---|---|
| 1 | tocca **Prenota a voce** e consenti il microfono | il pulsante diventa l'orb; saluto «Come posso aiutarla?» |
| 2 | «Che orari avete?» | risposta con gli orari, **senza** chiedere dati |
| 3 | «Avete piatti vegetariani?» | elenco dal menu vero |
| 4 | «Vorrei prenotare un tavolo per due domani alle venti» | «Mi dice il suo nome e un numero di telefono?» |
| 5 | «Mario Rossi, 333 123 4567» → «sì» | registrazione, poi il bot riprende la richiesta e chiede conferma |
| 6 | «sì» | codice `RES-…` e **referto finale** a voce + **popup** a schermo |
| 7 | «sì, tutto corretto» | il popup sparisce **4 secondi dopo** |
| 8 | interrompi il bot mentre parla | si ferma subito (barge-in) |
| 9 | «Sono celiaco, cosa posso mangiare?» | risposta dal menu, mai inventata |

**Pagina di test** `http://localhost:8003/test-voice`: tab **STATO** (controlli), tab **TECNICA** (spiegazione), elenco eventi e trascrizione.

### 4.3 Diagnosi

| Strumento | Cosa dice |
|---|---|
| `python -m voicebot doctor` | 12 controlli (python, .env, pacchetti, STT, TTS, VAD, anonimizzatore, audio, **BE**, registrazione, porta, dispositivi) con il rimedio per ciascuno |
| `http://localhost:8003/diag` | lo stesso report in JSON |
| Log del voice | JSON a una riga; `LOG_LEVEL=DEBUG` per più dettagli |
| Log del BE | nel terminale: scelta del modello, warm-up, errori |

---

## 5. Sessioni live per la presentazione

### 5.1 Il giorno prima

- [ ] Le tre macchine sono sulla **stessa rete**, con **IP stabili** (statici o DHCP riservati).
- [ ] `git pull` fatto su tutte; un giro completo di `avvia.py` già eseguito su ciascuna (ruolo e IP-BE ricordati).
- [ ] Sul BE: `ollama list` mostra il modello; `python -m backend.check_model` = 8/8; `python -m backend.maintenance backup`.
- [ ] Sul BE: `STAFF_API_KEY` impostata (`python -m backend.maintenance staff-key`).
- [ ] Firewall aperto sulle porte del ruolo di ciascun PC.
- [ ] Facoltativo ma consigliato: `python lan\machine_setup.py --installa-avvio` su ogni macchina (partono al login).
- [ ] Prova generale completa con la checklist 4.2.

### 5.2 Il giorno della demo (sequenza)

1. Accendere i PC. Se è stato installato l'avvio automatico, i componenti partono da soli **30 secondi dopo il login** (CHAT e VOICE aspettano il BE).
   Altrimenti, su ciascun PC: `python entrypoint\avvia.py` (il **BE per primo**).
2. Sul PC del **presentatore**: `python entrypoint\avvia.py --attendi` → attende finché compare **`TUTTO OK`**.
3. Aprire le pagine della demo (vedi 5.3).
4. Il riscaldamento avviene da solo (il BE carica il modello, il VOICE manda un turno finto): su un PC debole aspetta **circa un minuto** dopo l'avvio del VOICE prima della prima domanda.

### 5.3 Cosa mostrare e in che ordine

| Momento | Dove | Cosa |
|---|---|---|
| Architettura | slide `00_presentazione_completa.pdf` | le tre macchine e il flusso |
| Chat scritta | `http://<IP_CHAT>:8501` o il sito `http://localhost:8080` (PC BE) | prenotazione con riepilogo e conferma |
| **Voce** | `http://localhost:8003/` **sul PC VOICE** | frase d'esempio 4.2, popup e referto |
| Dietro le quinte | `http://localhost:8003/test-voice` | eventi, trascrizione, STATO |
| Il ristoratore | `http://<IP_BE>:8000/api/staff` | la prenotazione appena fatta con nome e telefono |
| Resistenza ai guasti | spegnere Ollama e riaccenderlo | messaggio gentile, poi tutto torna |

### 5.4 Piano B

| Se… | Allora… |
|---|---|
| il microfono non parte nel browser | stai usando un indirizzo non sicuro: apri `http://localhost:8003/` sul PC VOICE, oppure `voice\voice live ws://<IP_VOICE>:8003/ws/voice` da un PC con microfono |
| la prima risposta è lunghissima | normale su CPU debole: il modello legge il prompt la prima volta (1–2 minuti); poi 1–5 s |
| il BE non risponde | `python entrypoint\avvia.py --status`; `ollama list`; riavvia il BE; il voice lo riaspetta da solo |
| il voice non parte | `python -m voicebot doctor` |
| nessuna rete | tutto su un solo PC: configurazione 6.2 |
| il BE è irraggiungibile ma devi mostrare il voice | `voice\voice local` (BE finto, banner «LOCAL TEST») |

---

## 6. Configurazioni di esecuzione

> **Quale scelgo?**
>
> | Voglio… | Configurazione |
> |---|---|
> | rispettare la **traccia** (tre macchine in rete) | **6.1** |
> | provare tutto su un solo PC | 6.2 |
> | provare il voice senza BE | 6.3 |
> | il voice su un PC e il BE su un altro | 6.4 |
> | parlare da un PC diverso da quello del voice | 6.5 |
> | usare il voice da terminale | 6.6 |
> | far passare il voice dalla CHAT | 6.7 |
> | girare su un PC con poca potenza | 6.8 |
> | usare Docker | 6.9 |

### 6.1 Configurazione principale (traccia): tre macchine separate in rete

**Cosa richiede la traccia (riassunto dai documenti del progetto):** tre componenti su **macchine diverse**, che comunicano **solo via rete** (HTTP/WebSocket), con **modelli in locale**; casi d'uso: prenotare, modificare, cancellare, menu e informazioni.

```
                  stessa rete locale (LAN)
   ┌────────────────┐        ┌────────────────┐        ┌────────────────┐
   │  PC  BE        │◄───────│  PC  CHAT      │        │  PC  VOICE     │
   │  :8000  :8080  │◄───────┼────────────────┼────────│  :8003         │
   │  FastAPI+LLM   │ HTTP   │  :8501  :8002  │        │  WebSocket     │
   │  Ollama, SQLite│        │  Streamlit+API │        │  Whisper+Piper │
   └────────────────┘        └────────────────┘        └────────────────┘
        parte PER PRIMO e resta acceso      CHAT e VOICE aspettano il BE
```

**Ordine obbligatorio:** **BE → (CHAT e VOICE, in qualunque ordine)**. CHAT e VOICE hanno un *cancello*: se il BE non risponde non partono (attendono fino a 180 s).

#### Preparazione una tantum (per ogni macchina)

1. **IP stabili** (statici o riservati sul router). Annotali: BE = ______ · CHAT = ______ · VOICE = ______.
2. Clona e fai il primo giro:
   ```bat
   git clone https://github.com/KsandarIV/AI_4_Restaurants.git
   cd AI_4_Restaurants
   python entrypoint\avvia.py
   ```
   Rispondi a **ruolo** e (su CHAT e VOICE) **IP del BE**. Se il BE non è ancora acceso, aggiungi `--no-wait`.
3. **Pubblica gli IP** (solo se sono statici), perché `--status` e `--attendi` conoscano le altre macchine. Su **ciascuna** macchina:
   ```bat
   python lan\machine_setup.py --pubblica-ip
   ```
   poi un solo PC fa `git add lan\lan_config.json` · `git commit -m "IP delle macchine"` · `git push`, e gli altri `git pull`.
4. **Avvio automatico** (consigliato): `python lan\machine_setup.py --installa-avvio` su ogni macchina.

#### Cosa deve fare ciascuna macchina

| | **PC BE** (per primo) | **PC CHAT** | **PC VOICE** |
|---|---|---|---|
| Ruolo | `be` | `chat` | `voice` |
| Prima | Ollama acceso (`ollama list` mostra il modello); `.env` con `OLLAMA_MODEL` e `STAFF_API_KEY` | BE già acceso | BE già acceso |
| Comando | `python entrypoint\avvia.py` | `python entrypoint\avvia.py` | `python entrypoint\avvia.py` |
| Si avvia | BE `:8000` + sito `:8080` | Streamlit `:8501` + API `:8002` | server `:8003` |
| Segnale di «pronto» | log: «Server pronto…» e «Modello pronto in memoria» | pagina Streamlit raggiungibile | `curl http://localhost:8003/ready` → `ready` |
| Firewall | 8000, 8080 | 8501, 8002 | 8003 |
| Si ferma con | `Ctrl+C` | `Ctrl+C` | `Ctrl+C` |

> **Nota.** Il modello viene caricato in memoria all'avvio del BE (warm-up). Il VOICE manda a sua volta un turno finto al BE
> per «scaldare» il prompt: il primo cliente non aspetta.

#### Verifica (dal PC del presentatore)

```bat
python entrypoint\avvia.py --attendi     :: aspetta e poi stampa la tabella; esce con 0 su "TUTTO OK"
python entrypoint\avvia.py --status      :: la tabella una volta sola
```

Poi, **da un altro PC**: `http://<IP_BE>:8000/api/health` → `"status":"online"`.

#### Durante la demo

- Chat: `http://<IP_CHAT>:8501`.
- Voce: **sul PC VOICE**, `http://localhost:8003/` (microfono consentito solo su `localhost`/HTTPS).
- Ristoratore: `http://<IP_BE>:8000/api/staff`.

#### Spegnimento

`Ctrl+C` in ogni terminale (prima CHAT e VOICE, per ultimo il BE). Togliere l'avvio automatico: `python lan\machine_setup.py --rimuovi-avvio`.

### 6.2 Un solo PC (sviluppo o demo di ripiego)

Tutti i componenti sulla stessa macchina, `BACKEND_BASE_URL=http://localhost:8000`.

```bat
python setup\setup_env.py --role all --yes
:: terminale 1 (Ollama acceso)
python -m backend.main
:: terminale 2
python -m voicebot
:: terminale 3 (facoltativo)
streamlit run chat\app.py
```

Apri `http://localhost:8003/`. Per ridurre il carico su un portatile usa anche 6.8.

> **Nota.** Con `avvia.py` su un solo PC puoi usare `--role be` in un terminale e `--role voice --no-wait` in un altro, ma il ruolo salvato in `macchina.json` è uno solo: per l'uso su un PC è più semplice avviare a mano come sopra.

### 6.3 Solo VOICE con BE finto (nessun altro componente)

```bat
voice\voice local            :: con Whisper e Piper veri
voice\voice local --fake     :: senza modelli: prova solo la pagina e il flusso
```

Apre `/test-voice` con il banner **«LOCAL TEST — BE finto»**: nessun dato reale viene toccato. Ideale per sviluppare e per le dimostrazioni senza rete.

### 6.4 VOICE su un PC, BE su un altro

Sul PC VOICE:

```bat
python entrypoint\avvia.py --role voice --be-host <IP_BE>
:: oppure, a mano:  in .env  BACKEND_BASE_URL=http://<IP_BE>:8000   poi   voice\voice real
```

`voice\voice real` controlla il BE, **lo aspetta** (60 s di default, `--wait N`) e poi avvia. Sul PC BE: `python -m backend.main` con la porta 8000 aperta.

### 6.5 Parlare da un PC diverso da quello del voice

Un browser su `http://<IP_VOICE>:8003/` **non** può usare il microfono (indirizzo non sicuro). Due soluzioni:

1. Aprire il sito **sul PC VOICE** (`http://localhost:8003/`), oppure
2. Sul PC con il microfono: `voice\voice live ws://<IP_VOICE>:8003/ws/voice` (client Python: microfono e casse locali, si riconnette da solo se la rete cade; `--half-duplex` se non hai le cuffie).

### 6.6 Voice da terminale (senza browser)

```bat
voice\voice v2               :: INVIO per parlare, «q» per uscire
voice\voice v2 --text        :: scrivi invece di parlare (non serve il microfono)
```

Una domanda, una risposta: è la modalità più semplice e più robusta per verificare l'integrazione col BE.

### 6.7 VOICE appoggiato al servizio CHAT

In `.env` del VOICE: `CHAT_SERVICE_URL=http://<IP_CHAT>:8002`. Allora la chat del sito del voice e la modalità `v2` passano da `chat/api.py` (stessa logica della chat scritta). Se vuota: la chat del sito risponde «non è collegato».

### 6.8 PC con poca potenza (portatile senza GPU)

Misurato su un portatile: primo turno di un cliente 41–75 s, poi 1–5 s. Per migliorare:

```bat
ollama create gemma4-voice -f voice\local_llm\Modelfile    :: stesso modello, contesto 8k, 6 thread
:: in .env del PC che esegue il BE:
::   OLLAMA_MODEL=gemma4-voice
::   OLLAMA_TIMEOUT_S=300
```

Aspetta circa un minuto dopo l'avvio del voice (warm-up). Se serve: `STT_MODEL=base` (più veloce, meno preciso su numeri e nomi). Chiudi browser e app pesanti: con poca RAM il sistema va in paging.

### 6.9 Docker (non verificato)

`voice\Dockerfile` (multi-stage, utente non-root, healthcheck) esiste ma **non è mai stato costruito** qui. Istruzioni nel file; richiede `BACKEND_BASE_URL` con l'IP LAN del BE (non `localhost`) e i modelli montati come volume.

---

## 7. Risoluzione dei problemi

| Sintomo | Causa probabile | Rimedio |
|---|---|---|
| `avvia.py` si ferma su `git pull` | modifiche locali o conflitti | `git status`; **non forzare**; chiedi al gruppo |
| `No module named …` all'avvio | venv incompleto | rilancia `python entrypoint\avvia.py` (o `setup_env.py --role <ruolo>`) |
| VOICE o CHAT non partono, «BE assente» | il BE è spento o l'IP è sbagliato | accendi il BE; `--be-host <IP>`; controlla il firewall della 8000 |
| «Non riesco a raggiungere il server» (a voce) | stesso | `python -m voicebot doctor` |
| «Il modello linguistico non risponde» (503) | Ollama spento o nessun modello con strumenti | `ollama serve`; `ollama list` |
| `/api/health` è `degraded` | DB o modello non rispondono | guarda i campi `database`, `llm_reachable`, `llm_model_available` |
| `/api/health` **non risponde** durante un turno | il BE è bloccato mentre l'LLM elabora (limite noto) | aspetta; non è un guasto |
| Prima risposta lentissima | l'LLM legge il prompt per un cliente nuovo (cache vuota) | normale su CPU debole; vedi 6.8 |
| «Chiamo get_menu…» detto a voce | il modello descrive lo strumento invece di usarlo | il voice lo filtra e riprova; se persiste, ripeti la domanda |
| Il microfono non parte | pagina non sicura (`http://IP…`) | usa `http://localhost:8003/` sul PC VOICE o `voice live` |
| Il bot non risponde, orb fermo | modelli ancora in caricamento o BE lento | guarda `/ready` e il tab STATO di `/test-voice` |
| `/api/staff` dice «disabilitata» | manca `STAFF_API_KEY` | `python -m backend.maintenance staff-key` e copia la riga nel `.env` del BE |
| `Port 8003 is in use` | un altro voice è già acceso | chiudilo (o cambia `VOICE_PORT`) |
| Il sito non vede la chat (porta 8002) | `chat/api.py` non avviato | avvia il ruolo `chat` con `avvia.py` |
| `git pull` dà `cannot lock ref` | riferimenti locali sporchi | `git fetch --prune` e riprova |
| Tutto nel `.env` sembra sbagliato | `.env` copiato da un altro PC | cancellalo e rilancia `avvia.py` |

> **Attenzione.** Non committare mai `.env`, `.venv\`, `lan\macchina.json`, `voice\models\` e i database: sono già nel `.gitignore`.

---

## 8. Appendici

### 8.1 Struttura delle cartelle

```
AI_4_Restaurants/
├── entrypoint/avvia.py        un comando per macchina (7 passi)
├── setup/                     venv condiviso, requisiti per ruolo, modelli
├── lan/                       ruoli, IP, porte, avvio automatico, stato
├── backend/                   BE: FastAPI, LangGraph, SQLite, Ollama
├── chat/                      CHAT: Streamlit, API del sito, anonimizzatore
├── voice/                     VOICE: pipeline vocale, sito, test, doctor
├── frontend/                  sito vetrina (HTML/JS statico)
├── tests/                     test del BE
├── docs/                      FLUSSO, HANDOFF, AGENTS e studio/voice (queste slide)
└── .env.example               modello del .env (il vero .env è locale)
```

### 8.2 File locali, mai in git

| File | Contiene |
|---|---|
| `.env` | configurazione della macchina (IP del BE, chiavi) |
| `.venv\` | ambiente Python |
| `lan\macchina.json` | ruolo, IP e nome della macchina |
| `voice\models\` | voce Piper |
| `backend\*.db` | database e conversazioni |

### 8.3 Glossario minimo

| Termine | Significato |
|---|---|
| **Cancello** | CHAT e VOICE non partono finché il BE non risponde a `/api/health` |
| **Warm-up** | turno finto al modello per farlo «scaldare» prima del primo cliente |
| **Barge-in** | interrompere il bot mentre parla |
| **Referto finale** | il bot rilegge a voce i dati veri della prenotazione e chiede un ultimo «sì» |
| **Servizio extra** | processo avviato insieme al componente principale (es. API della CHAT sulla 8002) |

### 8.4 Note e limiti noti

1. La prova **a tre macchine dal vivo** non è ancora stata fatta: la sezione 6.1 è costruita sul codice, non su una prova reale.
2. Gli IP in `lan\lan_config.json` sono esempi finché non vengono pubblicati (6.1, passo 3).
3. L'API del BE è aperta in LAN (solo l'area staff ha una chiave) e il CORS è `*` di default.
4. Il voice trascrive una frase alla volta (modello condiviso con un lock) e c'è un solo LLM: più chiamate in parallelo si mettono in coda.
5. Il riconoscimento vocale segue `VOICE_LANGUAGE`: altre lingue non sono trascritte bene.
6. Il BE non risponde mentre un turno di streaming è in corso (anche `/api/health`): segnalato al team BE.
7. Il `Dockerfile` del voice non è stato costruito.

*Manuale generato da `docs/studio/voice/_sorgenti/manuale_src.md`: l'indice si rigenera con `python _sorgenti/gen_manual.py`.*
