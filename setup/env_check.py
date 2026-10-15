"""Hook chiamato all'avvio di ciascuna pipeline (BE / CHAT / VOICE).

Uso (3 righe all'inizio del main di ogni componente):
    from env_check import ensure_environment  # sys.path deve includere setup/
    if not ensure_environment():
        raise SystemExit(3)  # setup eseguito o rifiutato: riavvia dopo il setup

Solo stdlib, nessun import delle dipendenze del venv: funziona anche a venv rotto.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SETUP_DIR = Path(__file__).resolve().parent
if str(SETUP_DIR) not in sys.path:
    sys.path.insert(0, str(SETUP_DIR))

from setup_env import is_setup, log, main as setup_main  # noqa: E402


def ensure_environment(interactive: bool | None = None, role: str | None = None) -> bool:
    """Ritorna True se l'ambiente e' pronto, altrimenti lancia il setup.

    Args:
        interactive: None = chiede solo se stdin e' un terminale; True/False forza.
        role: be|chat|voice = verifica/installa solo base + ruolo (venv leggero);
              None = ruolo salvato o tutto.
    """
    if is_setup(role):
        return True
    if os.environ.get("VOICE_SETUP_SKIP") == "1":
        log("check saltato via VOICE_SETUP_SKIP=1 (l'ambiente potrebbe essere incompleto).")
        return True
    if interactive is None:
        interactive = sys.stdin.isatty()
    if interactive:
        log("ambiente non configurato: avvio setup interattivo...")
        code = setup_main(["--role", role] if role in ("be", "chat", "voice") else [])
        if code != 0:
            log("setup non completato: sistema gli errori e riavvia il componente.")
            return False
        log("setup completato: RIAVVIA il componente per usare il venv aggiornato.")
        return False
    log("ambiente non configurato e sessione non interattiva: "
        "lancia 'python setup\\setup_env.py' e riavvia.")
    return False
