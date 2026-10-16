# Tutti i siti e le pagine del progetto

Elenco di **ogni indirizzo** utilizzabile, cosa c'è dentro e su quale macchina funziona. I link sono cliccabili
(da GitHub o dall'anteprima Markdown di VS Code) e valgono **sul PC dove il servizio è acceso**: per aprirli da un altro PC
sostituite `localhost` con l'IP di quella macchina (vedi [le porte](#porte-e-firewall)).

> I nomi `*.localhost` (es. `completo.localhost`) significano "questo PC" e il browser li considera **pagine sicure**:
> è l'unico modo per avere il **microfono** senza HTTPS. Si aprono da soli con `python entrypoint\avvia.py`.

## 1. I siti da mostrare (si aprono da soli, su ogni macchina: pagina di test del ruolo + sito completo)

| Macchina | Sito | Link | Cosa c'è dentro |
|---|---|---|---|
| **BE** | Sito **senza** chat/voce funzionanti | [solo-be.localhost:8080](http://solo-be.localhost:8080/) | il sito del ristorante (`frontend/`): menu, orari, dove siamo; chat e voce compaiono in basso a destra ma non rispondono |
| **BE** (e da CHAT e VOICE come `https://<IP-BE>:8090/`) | Sito **completo**, servito **dal BE** | [completo.localhost:8090](https://completo.localhost:8090/) | pulsante **voce** con orb animato, finestrella **chat**, menu, **Le mie prenotazioni**, riepilogo finale a voce, **Area ristoratore**, Swagger e salute del BE. Chat e voce parlano con i PC CHAT e VOICE (indirizzi trovati e verificati da soli: `python -m showcase.peers show`) |
| **CHAT** | Sito del collega chat | [chat.localhost:8080](http://chat.localhost:8080/) | `frontend/` con la chat che funziona (finestrella), menu, orari |
| **VOICE** | Pagina di test della voce | [voce.localhost:8003/test-voice](http://voce.localhost:8003/test-voice) | orb animato, schede laterali **STATO** (controlli, BE, modelli, eventi) e **TECNICA** (schede tecniche) |

Per non aprire il browser da soli: `set AI4R_NO_BROWSER=1`.

### Quale indirizzo uso adesso?

| Voglio… | Vado su | Note |
|---|---|---|
| provare la **voce** (anche le soglie anti-rumore) sul PC voce | [voce.localhost:8003/test-voice](http://voce.localhost:8003/test-voice) | la tua voce va direttamente al tuo server voce; è la pagina da usare per tarare `BARGE_IN_MIN_MS`, `VAD_MIN_SPEECH_MS`, `VAD_ENERGY_THRESHOLD` (nel `.env`, poi riavviare il voice) |
| il sito col pulsante voce, solo del PC voce | [localhost:8003/](http://localhost:8003/) | stesse soglie; senza database né area ristoratore del BE centrale |
| **tutto insieme** (voce + chat + area ristoratore + database) | `https://<IP-BE>:8090/` — sul BE [completo.localhost:8090](https://completo.localhost:8090/) | serve il gateway acceso sul BE (`avvia.py`); al primo accesso: Avanzate → Procedi |
| il sito della chat | [chat.localhost:8080](http://chat.localhost:8080/) | sul PC chat |
| capire cosa non va | [localhost:8003/diag](http://localhost:8003/diag) · `voice\voice doctor` · `python -m showcase.peers show` | |

`python entrypoint\avvia.py` **apre da solo** le pagine; `voice\voice real` (solo il voice, senza toccare gli altri) **non apre il browser**: apri tu la pagina di test e
aspetta che nel terminale compaia "models ready" (finché i modelli non sono caricati la pagina dice "Carico i modelli vocali…"). `voice real` non si annuncia al gateway:
se il sito completo non vede la voce, sul BE: `python -m showcase.peers set voice <IP-VOICE>`.

### Indirizzi su questa rete (oggi — aggiornare se gli IP cambiano)

| Macchina | IP | Pagine (da un altro PC senza microfono, o dal PC stesso) |
|---|---|---|
| **BE** | `10.10.95.34` | [sito completo](https://10.10.95.34:8090/) · [Swagger](http://10.10.95.34:8000/docs) · [salute BE](http://10.10.95.34:8000/api/health) · [sito `frontend/`](http://10.10.95.34:8080/) · [area ristoratore (BE)](http://10.10.95.34:8000/api/staff) |
| **VOICE** | `10.10.93.153` | [test voce](http://10.10.93.153:8003/test-voice) · [sito voce](http://10.10.93.153:8003/) · [diagnosi](http://10.10.93.153:8003/diag) · [pronto?](http://10.10.93.153:8003/ready) |
| **CHAT** | da `python -m showcase.peers show` sul BE | `:8501` Streamlit · `:8002/health` API · `:8080` il suo sito |

Da questi indirizzi con IP il **microfono non funziona** (il browser lo concede solo su `localhost`, `*.localhost` e `https://`): per parlare usate gli indirizzi
`*.localhost` o il sito completo in HTTPS. Le pagine di sola lettura (diagnosi, Swagger, salute) vanno bene da qualunque PC.

## 2. Pagine del servizio VOICE (porta 8003)

| Pagina | Link | Cosa c'è dentro |
|---|---|---|
| Sito voce | [localhost:8003/](http://localhost:8003/) | stesso sito completo, servito dal server voce (il microfono funziona solo da `localhost`) |
| Test voce | [localhost:8003/test-voice](http://localhost:8003/test-voice) | orb + schede STATO / TECNICA, trascrizione in diretta, pop-up della prenotazione; banner **VOICE / TESTS** con il BE in uso. I vecchi `/prova-vocale` e `/prova-vocale-test` portano qui |
| Scheda tecnica | [localhost:8003/tech](http://localhost:8003/tech) | modelli, logica, punti di forza e deboli (stampabile in PDF) |
| Come è fatto il codice | [localhost:8003/tech-codice](http://localhost:8003/tech-codice) | la pipeline file per file |
| L'idea in parole semplici | [localhost:8003/tech-idea](http://localhost:8003/tech-idea) | per chi non è tecnico (ristoratore) |
| Diagnosi | [localhost:8003/diag](http://localhost:8003/diag) | JSON con tutti i controlli: BE raggiungibile, registrazione, modelli, microfono |
| Pronto? | [localhost:8003/ready](http://localhost:8003/ready) | 200 = modelli caricati **e** BE raggiungibile |
| Salute | [localhost:8003/health](http://localhost:8003/health) | `{"status":"ok"}` |

Il sito sulla 8003 e il sito completo sulla 8090 sono la **stessa pagina**: il primo parla direttamente con questo server voce, il secondo passa dal gateway
sul BE (database, area ristoratore, chat). Per la demo a tre macchine usate il completo.

Da riga di comando: `voice\voice doctor` (cosa non va), `voice\voice local` (test locale con BE finto, apre [la pagina di test](http://localhost:8003/test-voice)).

## 3. Pagine del BE (porta 8000)

| Pagina | Link | Cosa c'è dentro |
|---|---|---|
| Swagger | [localhost:8000/docs](http://localhost:8000/docs) | tutti gli endpoint, provabili dal browser |
| Salute | [localhost:8000/api/health](http://localhost:8000/api/health) | stato, modello LLM, database |
| Area ristoratore (BE) | [localhost:8000/api/staff](http://localhost:8000/api/staff) | prenotazioni con **nome e telefono**, chiusure, piatti esauriti. Serve `STAFF_API_KEY` |
| Menu | [localhost:8000/api/menu](http://localhost:8000/api/menu) | JSON del menu |
| Informazioni | [localhost:8000/api/info](http://localhost:8000/api/info) | indirizzo, orari, telefono |

## 4. Pagine della CHAT (porte 8501 e 8002)

| Pagina | Link | Cosa c'è dentro |
|---|---|---|
| Chat Streamlit | [localhost:8501](http://localhost:8501/) | la chat testuale autonoma (registrazione, anonimizzazione, prenotazione) |
| API della chat | [localhost:8002/health](http://localhost:8002/health) | usata dal sito; [localhost:8002/docs](http://localhost:8002/docs) per provarla |

## 5. Il sito di `frontend/` (porta 8080)

| Pagina | Link | Cosa c'è dentro |
|---|---|---|
| Home | [localhost:8080](http://localhost:8080/) | sito del ristorante con assistente chat |
| Area ristoratore | [localhost:8080/staff.html](http://localhost:8080/staff.html) (anche su [completo.localhost:8090/staff.html](https://completo.localhost:8090/staff.html)) | tabella delle prenotazioni con nome e telefono; si entra con la chiave `STAFF_API_KEY` del BE. Una prenotazione compare **solo se è stata confermata fino in fondo**: un cliente solo registrato non compare |

## Porte e firewall

| Servizio | Porta | Macchina |
|---|---|---|
| BE (API) | 8000 | BE |
| Sito `frontend/` | 8080 | BE e CHAT |
| Sito completo (gateway HTTPS) | 8090 | BE; gli altri PC lo aprono su `https://<IP-BE>:8090/` |
| API chat | 8002 | CHAT |
| Chat Streamlit | 8501 | CHAT |
| Voce (sito, test, WebSocket) | 8003 | VOICE |

Il BE deve avere aperte **8000, 8080 e 8090** in ingresso (`avvia.py` le crea o stampa i comandi `netsh`). Da un altro PC: `http://<IP-macchina>:<porta>/…` (le pagine senza microfono). Il **microfono** funziona solo su `localhost`
o `*.localhost`: usate gli indirizzi della sezione 1.

## Se un indirizzo non si apre

1. **Siete sul ramo giusto?** Le novità (sito completo, apertura automatica) sono sul ramo che contiene `showcase/`.
   Se siete su un ramo che non le ha, non esistono: `git branch --show-current`, poi `git pull`.
2. **Un vecchio processo occupa la porta.** Se un servizio di una prova precedente è ancora acceso, il nuovo non parte
   (porte 8003, 8080, 8090): chiudete le finestre vecchie oppure
   `Get-NetTCPConnection -LocalPort 8003,8080,8090 -State Listen | % { Stop-Process -Id $_.OwningProcess -Force }`.
3. **Il sito parte ma il BE no:** [localhost:8003/diag](http://localhost:8003/diag) dice cosa manca; `python entrypoint\avvia.py --status` guarda le tre macchine.
