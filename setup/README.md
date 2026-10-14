# setup — venv condiviso + modelli locali (Windows, Python puro)

Un solo venv in `AI_4_Restaurants/.venv`, condiviso da BE / CHAT / VOICE, più
setup guidato dei modelli locali (Ollama + voce Piper). Solo stdlib.

## Uso

```bat
REM prima volta su una macchina (chiede conferma a ogni passo: venv, pip, pull Ollama, voce Piper)
python setup\setup_env.py

REM accetta tutto senza chiedere (demo)
python setup\setup_env.py --yes

REM solo verifica (usato dalle pipeline)
python setup\setup_env.py --check-only
```

Salta singoli passi: `--skip-requirements --skip-ollama --skip-piper`.
Variabile d'emergenza: `VOICE_SETUP_SKIP=1` salta il check all'avvio.
Pacchetti marcati OPZIONALI in `requirements.txt` (es. `webrtcvad`, che richiede
MSVC per compilare): se falliscono, il setup continua con warning e li elenca
nel riepilogo + in `.venv/.setup_state.json`.

## Hook nelle 3 pipeline

All'inizio del `main` di ogni componente (BE, CHAT, VOICE):

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[<N>] / "setup"))
from env_check import ensure_environment
if not ensure_environment():
    raise SystemExit(3)  # setup appena eseguito o da completare: riavvia
```

`<N>` = livelli da risalire per arrivare alla root `AI_4_Restaurants`.
Il check è veloce (confronta `.venv/.setup_state.json` con `requirements.txt`):
se un collega aggiorna `requirements.txt`, al prossimo avvio il setup riparte da solo.

## File

- `setup_env.py` — script interattivo (crea `.venv`, `pip install -r requirements.txt`
  + editable install di `voice/`/`be/`/`chat/` se hanno `pyproject.toml`,
  check `ollama` + `ollama pull gemma4:12b`, download voce Piper in `voice/models/`).
- `env_check.py` — `ensure_environment()` per le pipeline.
- `requirements.txt` — dipendenze unificate dei 3 componenti (fonte di verità;
  `voice/pyproject.toml` la rispecchia per il build Docker).
- Il `.env` è unico in root (vedi `../.env.example`); `voicebot.config.find_env_file()`
  lo trova anche lanciando da `voice/`.
