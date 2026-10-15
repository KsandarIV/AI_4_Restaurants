# entrypoint — UN comando per macchina (Windows, solo stdlib)

```bat
python entrypoint\avvia.py [--role be|chat|voice] [--be-host IP]
```

Fa tutto in ordine e si ferma con istruzioni chiare al primo problema:

| # | Passo | Dettaglio |
|---|---|---|
| 1 | `git pull --ff-only` | codice aggiornato (solo fast-forward: se ci sono conflitti NON li fonde da solo) |
| 2 | `setup/` per ruolo | venv leggero (base + ruolo; `all` = tutto per sviluppo/test) |
| 3 | identità | ruolo chiesto una sola volta + IP auto-rilevato → `lan/macchina.json` |
| 4 | `.env` | IP del BE chiesto una volta e ricordato |
| 5 | firewall | regola per la porta del ruolo (o comando da admin) |
| 6 | attesa BE | solo chat/voice: parte solo quando il BE risponde |
| 7 | avvio | componente in foreground, log live, `Ctrl+C` per fermare |

Varianti:

```bat
python entrypoint\avvia.py --status            :: ping HTTP alle 3 macchine
python entrypoint\avvia.py --attendi           :: PRESENTATORE: aspetta tutte le macchine (un solo PC)
python entrypoint\avvia.py --sono --role X    :: identifica e basta
python entrypoint\avvia.py --no-git --no-wait :: salta git e attesa BE
python entrypoint\avvia.py --yes               :: risponde sì a tutto nel setup
```

## Presentazione con un solo PC (procedure pre-inizializzazione, una tantum)

Obiettivo: il giorno della demo si accendono i PC e il presentatore tocca **un solo PC**.
Configurazione manuale (una volta sola per macchina, poi tutto automatico):

1. **IP stabili**: statici o DHCP riservati sul router (altrimenti a ogni riavvio cambia tutto).
2. **Su ogni macchina**: `git clone` + un giro completo di `avvia.py`
   (risponde a ruolo e IP-BE una volta sola; risposte ricordate in `lan/macchina.json` + `.env`).
3. **Firewall una tantum** da admin (comando stampato dallo script, porte 8000/8501/8003).
4. **BE**: `ollama pull gemma4:12b` verificato. **CHAT**: `python -m spacy download it_core_news_md`
   (lo fa anche il setup per il ruolo chat, ma verificalo).
5. **Avvio automatico**: `python lan\machine_setup.py --installa-avvio` su ogni macchina
   (Scheduled Task al login +30 s). Da qui in poi basta accendere i PC.

Il giorno della demo, dal PC del presentatore:

```bat
python entrypoint\avvia.py --attendi   :: aspetta TUTTO OK, poi si parte
```

Ordine garantito dal sistema: le macchine partono da sole al login, chat/voice
attendono il BE (cancello automatico), il presentatore vede `TUTTO OK` e inizia.
Nessuno deve stare alle altre tastiere.

## Comandi git per le 3 macchine (prima prova)

**Prima volta su una macchina:**

```bat
git clone https://github.com/KsandarIV/AI_4_Restaurants.git
cd AI_4_Restaurants
python entrypoint\avvia.py
```

**Aggiornamenti (prima di ogni prova):** basta rilanciare `avvia.py`
(fa `git pull --ff-only` da solo). Equivalente manuale:

```bat
git pull            :: prende il codice aggiornato
```

**Chi modifica il codice** (una macchina alla volta, per non pestarsi):

```bat
git status --short              :: cosa ho cambiato
git add <cartella/file>         :: solo i file che servono
git commit -m "cosa ho fatto"
git push
```

**Regole per non fare casini dal vivo:**
- un push alla volta; gli altri fanno `pull` (o rilanciano `avvia.py`) prima di toccare codice;
- mai `git reset --hard` / `git checkout origin/main -- <file>` senza backup (buttano lavoro);
- se `git pull` fallisce per conflitti: NON forzare — chiamate tutti e risolvete insieme
  (`git status` dice quali file; tenete una versione per file con `git checkout --ours/--theirs -- <file>`);
- file locali (`.env`, `.venv/`, `lan/macchina.json`, `voice/models/`, DB) NON si committano mai
  (sono già nel `.gitignore`): ogni macchina li genera da sola.
