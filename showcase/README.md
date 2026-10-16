# showcase — i siti della demo, aperti da soli

Cartella **nuova e autonoma**: non tocca `frontend/`, `chat/`, `backend/`, `voice/` (salvo CORS e `window.VOICE_BASE` nel sito voce),
quindi nessun merge può andare in conflitto per colpa sua. L'unico aggancio è un blocco in `lan/machine_setup.py`
(`start_component`) che chiama `showcase.launcher.start_showcase()`; se fallisce, il componente parte lo stesso.

## Topologia: una stella con il BE al centro

CHAT e VOICE **non si parlano mai tra loro**: tutto ciò che serve al sito completo passa dal **gateway sul BE**
(`showcase/gateway.py`, reverse proxy), come chiede la traccia.

```
 browser di QUALSIASI PC --HTTPS--> gateway sul BE  https://<IP-BE>:8090
                                       |--> BE        127.0.0.1:8000   /api/*, /docs      database, area ristoratore, Swagger
                                       |--> VOICE PC  :8003            /voice/*  + WebSocket /voice/ws/voice
                                       '--> CHAT PC   :8002            /voice/site/chat/*   la finestrella chat
```

Perché un reverse proxy invece di una copia del sito su ogni PC: **una sola origine** (niente CORS, un solo certificato, un solo
punto dove aggiungere autenticazione, rate limiting e log); i client non conoscono mai dove stanno VOICE e CHAT (possono cambiare
IP senza toccare nessun browser); **HTTPS termina qui**, ed è ciò che dà un *secure context* (quindi il **microfono**) ai PC CHAT e VOICE.

## Cosa succede con `python entrypoint\avvia.py`

Su ogni macchina, oltre al componente del ruolo, partono i servizi e si apre il browser **da soli**: la **pagina di test del proprio
ruolo** e il **sito completo**.

| Macchina | Si apre | Cos'è |
|---|---|---|
| **BE** | `http://solo-be.localhost:8080/` | il sito **senza** chat/voce funzionanti: compaiono in basso a destra (`frontend/`, com'era) |
| **BE** | `https://completo.localhost:8090/` | il sito **completo** (il gateway parte qui): voce con orb animato, chat, prenotazioni, **Area ristoratore**, Swagger e salute del BE |
| **CHAT** | `http://chat.localhost:8080/` + `https://<IP-BE>:8090/` | il suo sito (`frontend/`, la chat funziona, parte da solo) + il sito completo **servito dal BE** |
| **VOICE** | `http://voce.localhost:8003/test-voice` + `https://<IP-BE>:8090/` | pagina di test: orb + schede **STATO** e **TECNICA** + il sito completo **servito dal BE** |

Tutti gli indirizzi, con link e contenuto: [docs/SITI.md](../docs/SITI.md). Per non aprire il browser: `set AI4R_NO_BROWSER=1`.

### Certificato (HTTPS autofirmato)
Al primo accesso il browser mostra un avviso: **Avanzate → Procedi**, una volta per browser. Il certificato (`lan/tls/`, mai su Git)
elenca nomi e IP del BE e si rigenera se l'IP cambia. In ambiente reale: mettere in `lan/tls/` `gateway.pem` e `gateway.key` emessi dalla
CA interna (o mkcert): non vengono sovrascritti. Dipendenza: `cryptography` (in `setup/requirements/be.txt`); in mancanza usa `openssl`
di Git; se non c'è nulla parte in HTTP e il microfono funziona solo da `localhost`.

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

## Perché `*.localhost` e HTTPS

Il microfono funziona solo su pagine "sicure": `http://localhost`, `*.localhost` e qualsiasi `https://`. `http://192.168.x.x` no. Sul BE basta
`completo.localhost`; dagli altri PC serve l'HTTPS del gateway.

## Il sito completo

È il sito voce (`voice/src/voicebot/pipeline/site/`): pulsante-orb che si trasforma con le sue animazioni, finestrella chat,
"Le mie prenotazioni", riepilogo finale a voce. Il gateway lo serve **leggendo i file a ogni richiesta**: dopo un `git pull`
basta ricaricare. Lo stesso gateway serve `staff.html` e gli asset di `frontend/` (sola lettura, percorsi confinati a `css/` e `js/`).

## Comandi manuali (se servono)

```bat
.venv\Scripts\python showcase\gateway.py                      :: gateway sul BE (https :8090)
.venv\Scripts\python showcase\gateway.py --no-tls             :: solo HTTP (il microfono funziona solo da localhost)
.venv\Scripts\python -m http.server 8080 --directory frontend  :: solo il sito di frontend/ (come prima)
voice\voice local                                              :: test della voce con BE finto
```

## Per non andare in conflitto

- ognuno modifica **solo la propria cartella**; i file di questa cartella li modifica solo chi cura la demo;
- prima di un push: `git pull --rebase origin main`; se Git segnala un conflitto in un file non tuo, **non risolverlo**: avvisa il proprietario;
- niente `git push --force` e niente lavoro diretto su `main`: PR dal proprio branch.
