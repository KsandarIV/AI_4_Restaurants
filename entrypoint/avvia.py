"""UNICO comando da lanciare su ogni macchina (solo stdlib, Windows).

    python entrypoint/avvia.py [--role be|chat|voice] [--be-host IP]

Fa tutto in ordine, fermandosi con un messaggio chiaro al primo problema:
  [1] git pull --ff-only  (codice aggiornato; --no-git per saltare)
  [2] setup/             (venv condiviso + modelli, interattivo se manca)
  [3] lan/macchina.json  (identita': ruolo chiesto una volta sola + IP auto)
  [4] .env di macchina   (IP del BE chiesto una volta sola e ricordato)
  [5] firewall           (regola porta del ruolo, o istruzioni da admin)
  [6] attesa BE          (solo chat/voice; il BE deve partire per primo)
  [7] avvio componente   (foreground, log live, Ctrl+C per fermare)

Altri usi:
  avvia.py --status            stato HTTP delle 3 macchine (non serve il ruolo)
  avvia.py --sono --role X     identifica e basta (scrive macchina.json)
  avvia.py --no-git --no-wait  salta aggiornamento codice e attesa BE
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ENTRYPOINT_DIR = Path(__file__).resolve().parent
ROOT = ENTRYPOINT_DIR.parent

sys.path.insert(0, str(ROOT / "setup"))
sys.path.insert(0, str(ROOT / "lan"))

import machine_setup as lan  # noqa: E402
from env_check import ensure_environment  # noqa: E402


def log(msg: str) -> None:
    print(f"[entrypoint] {msg}", flush=True)


def banner(title: str) -> None:
    print(f"\n{'=' * 64}\n[entrypoint] {title}\n{'=' * 64}", flush=True)


def git_pull() -> bool:
    """Aggiorna il codice: solo fast-forward (mai merge automatici sporchi)."""
    log("aggiorno il codice (git pull --ff-only)...")
    try:
        proc = subprocess.run(
            ["git", "pull", "--ff-only"], cwd=str(ROOT),
            capture_output=True, text=True, timeout=300,
        )
    except FileNotFoundError:
        log("AVVISO: git non trovato: continuo col codice locale (aggiornalo a mano).")
        return True
    print(proc.stdout.strip() or "(nessun output)")
    if proc.returncode != 0:
        log("git pull fallito (conflitti o rete?). Sistemalo a mano:")
        print((proc.stderr or "").strip()[-1500:])
        log("Comandi utili: git status / git stash / git pull (manuale).")
        return False
    log("codice aggiornato.")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Avvio completo di una macchina (git+setup+lan).")
    parser.add_argument("--role", choices=["be", "chat", "voice"], help="forza il ruolo")
    parser.add_argument("--be-host", default=None, help="IP LAN del BE")
    parser.add_argument("--no-git", action="store_true", help="salta git pull")
    parser.add_argument("--no-wait", action="store_true", help="non attendere il BE")
    parser.add_argument("--yes", "-y", action="store_true", help="risponde si' a tutto nel setup")
    parser.add_argument("--status", action="store_true", help="stato HTTP delle 3 macchine ed esci")
    parser.add_argument("--sono", action="store_true", help="identifica e basta (scrive macchina.json)")
    args = parser.parse_args(argv)

    config = lan.load_config()
    if args.status:
        return lan.cmd_status(config, args.be_host, lan.load_identity())

    banner(f"Avvio macchina  |  root={ROOT}")
    if not args.no_git and not git_pull():
        return 1

    banner("Setup ambiente (venv + modelli)")
    if args.yes:
        import setup_env

        setup_env.ASSUME_YES = True
    if not ensure_environment():
        log("setup non completato: sistema e rilancia entrypoint/avvia.py.")
        return 1

    banner("Identita' macchina (ruolo + IP)")
    role = lan.resolve_role(args.role)
    lan.ASSUME_IP = bool(args.sono)
    identity = lan.ensure_identity(role)
    if args.sono:
        return lan.cmd_show(config, identity)

    banner("Configurazione rete (.env + firewall)")
    if not lan.configure_env(role, config, args.be_host):
        return 1
    lan.firewall_hint(role, config)

    if role in ("chat", "voice") and not args.no_wait:
        banner("Attesa BE (fulcro)")
        if not lan.wait_for_be():
            log("BE assente: componente NON avviato. Accendi il BE e rilancia (o --no-wait).")
            return 1

    banner(f"Avvio {role} (Ctrl+C per fermare)")
    return lan.start_component(role, config)


if __name__ == "__main__":
    raise SystemExit(main())
