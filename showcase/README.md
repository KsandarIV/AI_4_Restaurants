# showcase — i siti della demo, aperti da soli

Cartella **nuova e autonoma**: non tocca `frontend/`, `chat/`, `backend/`, `voice/`, quindi nessun merge può andare
in conflitto per colpa sua. L'unico aggancio è un blocco in `lan/machine_setup.py` (`start_component`) che chiama
`showcase.launcher.start_showcase()`; se fallisce, il componente parte lo stesso.

## Cosa succede con `python entrypointvvia.py`

Su ogni macchina, oltre al componente del ruolo, partono i siti e si apre il browser **da soli**: la **pagina di test del proprio
ruolo** e il **sito completo**.

| Macchina | Si apre | Cos'è |
|---|---|---|
| **BE** | `http://solo-be.localhost:8080/` | il sito **senza** chat/voce funzionanti: compaiono in basso a destra (`frontend/`, com'era) |
| **CHAT** | `http://chat.localhost:8080/` | il sito del collega (`frontend/`) con la chat che funziona — parte da solo |
| **VOICE** | `http://voce.localhost:8003/test-voice` | pagina di test della voce: orb + schede **STATO** e **TECNICA** |
| **tutte** | `http://completo.localhost:8090/` | il sito **completo**: voce con orb animato, finestrella chat, prenotazioni, **Area ristoratore** (`/staff.html`), Swagger e salute del BE |

Tutti gli indirizzi, con link e contenuto: [docs/SITI.md](../docs/SITI.md). Per non aprire il browser: `set AI4R_NO_BROWSER=1`.

## Dove sono gli altri PC (scoperta dei servizi, `showcase/peers.py`)

Gli IP in `lan/lan_config.json` sono **esempi** (192.168.1.x): su una LAN reale puntano a host inesistenti. Perciò nessun
indirizzo è mai creduto: è **verificato**. Per ogni servizio remoto si prova, nell'ordine, e vince il primo che **risponde con la
firma del servizio** (un campo che solo quel servizio restituisce: BE `restaurant` su `/api/health`, chat `be_url` su `/health`,
voce `require_registration` su `/site/config`):

1. variabile `AI4R_<RUOLO>_HOST` (forzatura dell'operatore);
2. cache locale `lan/peers.json` (ignorata da Git), riverificata a ogni uso e scartata se non risponde;
3. l'indirizzo di `lan_config.json`, solo se risponde;
4. scansione limitata delle sottoreti /24 di questo PC e del BE (128 sonde in parallelo, qualche secondo).

Il risultato viene riletto **a ogni caricamento della pagina**: si può accendere il PC voce dopo, o cambiare IP, senza riavviare nulla.
Il server voce trova da solo il PC chat allo stesso modo (`AI4R_PEERS_FILE`); `CHAT_SERVICE_URL` nel `.env`, se impostato, ha la precedenza.

```bat
python -m showcase.peers show                     :: cosa si sa e se risponde adesso
python -m showcase.peers scan                     :: riscopre voce e chat
python -m showcase.peers set voice 10.10.95.50    :: fissa un indirizzo (solo se risponde davvero)
```

Se il PC voce non si trova, il sito completo mostra un avviso giallo con questo comando invece di una pagina muta.

## Perché `*.localhost`

Il microfono funziona solo su pagine "sicure". `http://localhost` e qualunque `*.localhost` lo sono; `http://192.168.x.x`
no. Per questo ogni PC serve il sito completo **sul proprio localhost** (`showcase/serve.py`) e il JavaScript parla via
rete con il PC voce (`ws://<IP-VOICE>:8003/ws/voice`, `/site/*`). Gli IP vengono da `lan/lan_config.json` e
dall'identità della macchina; sul PC voce il server imposta da solo `CHAT_SERVICE_URL=http://<IP-CHAT>:8002`
(la finestra chat del sito completo passa dal server voce al servizio chat).

## Il sito completo

È il sito voce (`voice/src/voicebot/pipeline/site/`): pulsante-orb che si trasforma con le sue animazioni, finestrella chat,
"Le mie prenotazioni", riepilogo finale. `showcase/serve.py` lo serve **leggendo i file a ogni richiesta**: dopo un
`git pull` basta ricaricare la pagina. Il server voce risponde con CORS aperto (rete locale di demo).

## Comandi manuali (se servono)

```bat
.venv\Scripts\python showcase\serve.py --voice http://<IP-VOICE>:8003     :: sito completo su :8090
.venv\Scripts\python -m http.server 8080 --directory frontend             :: solo il sito di frontend/ (come prima)
voice\voice local                                                         :: test della voce con BE finto
```

## Per non andare in conflitto

- ognuno modifica **solo la propria cartella**; i file nuovi di questa cartella li modifica solo chi cura la demo;
- prima di un push: `git pull --rebase origin main`; se Git segnala un conflitto in un file non tuo, **non risolverlo**: avvisa il proprietario;
- niente `git push --force` e niente lavoro diretto su `main`: PR dal proprio branch.
