# showcase — i siti della demo, aperti da soli

Cartella **nuova e autonoma**: non tocca `frontend/`, `chat/`, `backend/`, `voice/`, quindi nessun merge può andare
in conflitto per colpa sua. L'unico aggancio è un blocco in `lan/machine_setup.py` (`start_component`) che chiama
`showcase.launcher.start_showcase()`; se fallisce, il componente parte lo stesso.

## Cosa succede con `python entrypoint\avvia.py`

Su ogni macchina, oltre al componente del ruolo, partono i siti e si apre il browser **da soli**:

| Macchina | Si apre | Cos'è |
|---|---|---|
| **BE** | `http://solo-be.localhost:8080/` | il sito **senza** chat/voce funzionanti: compaiono in basso a destra (`frontend/`, com'era) |
| **BE** | `http://completo.localhost:8090/` | il sito **completo**: chat e voce funzionano parlando con i PC CHAT e VOICE |
| **CHAT** | `http://chat.localhost:8080/` | il sito del collega (`frontend/`) con la chat che funziona — parte da solo, non serve più `python -m http.server 8080 --directory frontend` |
| **VOICE** | `http://voce.localhost:8003/test-voice` | la pagina di test della voce: orb + schede **STATO** e **TECNICA** |

Il sito **completo** (`completo.localhost:8090`) si può aprire **anche su CHAT e VOICE**: ogni macchina lo serve da sé.
Per disattivare l'apertura automatica: `set AI4R_NO_BROWSER=1`.

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
