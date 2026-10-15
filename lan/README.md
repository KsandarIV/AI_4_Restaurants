# lan — setup e avvio delle 3 macchine (Windows, Python puro, solo stdlib)

Stesso script su tutte le macchine: riconosce il proprio ruolo e avvia il componente giusto.
**Via consigliata: `python entrypoint\avvia.py`** (fa anche git pull + setup prima).
Uso diretto (stessa macchina, codice già aggiornato):

## Primo giro su ogni macchina

```bat
git pull
python lan\machine_setup.py
```

1. chiede il ruolo (be/chat/voice) una sola volta → salvato in `lan/macchina.json`
   insieme all'**IP auto-rilevato** (file locale, **non** committato);
2. riusa `setup/` (crea `.venv` + modelli se mancano);
3. chiede l'IP LAN del BE → scrive il `.env` di quella macchina;
4. mostra/applica la regola firewall per la sua porta;
5. avvia il componente in foreground (log live, `Ctrl+C` per fermare).

Comandi utili:

```bat
python lan\machine_setup.py --role voice --start   :: avvio diretto
python lan\machine_setup.py --sono --role voice    :: identifica e basta (scrive macchina.json)
python lan\machine_setup.py --mostra-identita      :: chi sono io + chi sono gli altri
python lan\machine_setup.py --pubblica-ip          :: fissa il mio IP nel json condiviso (solo IP statici)
python lan\machine_setup.py --status               :: ping HTTP a be/chat/voice
python lan\machine_setup.py --be-host 192.168.1.10 --configure-only
python lan\machine_setup.py --write-launcher       :: crea AVVIA_<RUOLO>.bat
python lan\machine_setup.py --installa-avvio       :: avvio automatico al login (una tantum, poi zero-touch)
python lan\machine_setup.py --rimuovi-avvio        :: toglie l'avvio automatico
python lan\machine_setup.py --role chat --no-wait --wait-timeout 60
set LAN_ROLE=be  +  python lan\machine_setup.py    :: ruolo da variabile (lab/demo)
```

Le macchine CHAT/VOICE **attendono il BE** (poll `/api/health` fino a 180 s) prima di
avviarsi: il BE parte per primo e deve restare su. `--no-wait` salta l'attesa.

## Mappa (modificabile in `lan_config.json`, senza codice)

| ruolo | porta | health | avvio |
|---|---|---|---|
| be | 8000 + 8080 | API + sito `frontend/` (servito dal BE, chiama chat/voice in LAN) |
| chat | 8501 + 8002 | Streamlit + `chat/api.py` (stesso terminale, `BE_URL` all'IP BE) |
| voice | 8003 | `/health` | `python -m voicebot` (+WS `/ws/voice`) |

## Prerequisiti rete (una tantum)

- Stessa LAN/Wi-Fi; IP possibilmente statici o DHCP riservati.
- BE in ascolto su `0.0.0.0` (già così in `backend/main.py` e `voicebot`).
- Firewall: porte **8000/8501/8002/8080/8003 TCP in ingresso** (lo script stampa i comandi `netsh`).
- Sul BE: `ollama serve` + `ollama list` con `gemma4:12b`.
