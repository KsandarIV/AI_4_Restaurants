"""Setup interattivo del venv condiviso (solo stdlib, Windows).

Uso:
    python tools\\env_setup\\setup_env.py            # interattivo, chiede a ogni passo
    python tools\\env_setup\\setup_env.py --yes      # accetta tutto (demo/CI)
    python tools\\env_setup\\setup_env.py --check-only   # exit 0 se tutto ok, 1 altrimenti

Passi (ognuno con conferma, salvo --yes):
  1. check interprete Python (>= 3.10, consigliato 3.11/3.12)
  2. creazione di <root>\\.venv (se assente)
  3. installazione di requirements.txt nel venv
  4. check Ollama installato + in esecuzione + pull modello locale
  5. download voce Piper locale (TTS del VOICE)
Lo stato e' registrato in <root>\\.venv\\.setup_state.json per il check veloce.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

SETUP_DIR = Path(__file__).resolve().parent
ROOT = SETUP_DIR.parents[1]  # .../AI_4_Restaurants
VENV_DIR = ROOT / ".venv"
REQ_FILE = SETUP_DIR / "requirements.txt"
STATE_FILE = VENV_DIR / ".setup_state.json"

MIN_PY = (3, 10)

# Modello locale servito da Ollama sul BE / macchina dedicata.
OLLAMA_MODEL = "gemma4:12b"

PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
PIPER_VOICE = "it/it_IT/riccardo/x_low/it_IT-riccardo-x_low"
PIPER_DIR = ROOT / "voice" / "models"

ASSUME_YES = False


def log(msg: str) -> None:
    print(f"[setup] {msg}", flush=True)


def ask(question: str, default_yes: bool = True) -> bool:
    """Conferma interattiva per ogni passo (saltata con --yes)."""
    if ASSUME_YES:
        return True
    suffix = "[S/n]" if default_yes else "[s/N]"
    try:
        answer = input(f"[setup] {question} {suffix} ").strip().lower()
    except EOFError:
        return default_yes
    if not answer:
        return default_yes
    return answer in ("s", "si", "sì", "y", "yes")


def run(cmd: list[str], timeout: int = 600) -> tuple[int, str]:
    """Esegue un comando, ritorna (exit_code, output)."""
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def venv_python() -> Path:
    return VENV_DIR / "Scripts" / "python.exe"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def step_python() -> bool:
    log(f"interprete: {sys.version.split()[0]} (richiesto >= {'.'.join(map(str, MIN_PY))})")
    if sys.version_info < MIN_PY:
        log("ERRORE: Python troppo vecchio, installa Python 3.11 o 3.12.")
        return False
    if sys.version_info >= (3, 14):
        log("AVVISO: Python 3.14, alcune ruote (onnxruntime/webrtcvad) potrebbero mancare: "
            "in caso di errore usa Python 3.11.")
    return True


def step_venv() -> bool:
    py = venv_python()
    if py.exists():
        log(f"venv esistente: {VENV_DIR}")
        return True
    if not ask(f"creo il venv condiviso in {VENV_DIR}?"):
        log("venv saltato: i passi successivi useranno il Python corrente.")
        return False
    log("creazione venv in corso (puo' richiedere un minuto)...")
    code, out = run([sys.executable, "-m", "venv", str(VENV_DIR)], timeout=300)
    if code != 0 or not py.exists():
        log(f"ERRORE creazione venv:\n{out}")
        return False
    log("venv creato.")
    return True


def target_python() -> str:
    py = venv_python()
    return str(py) if py.exists() else sys.executable


def step_requirements(python: str) -> bool:
    if not REQ_FILE.exists():
        log(f"ERRORE: {REQ_FILE} non trovato.")
        return False
    if not ask(f"installo {REQ_FILE.name} con {python}?"):
        return True
    log("upgrade pip...")
    run([python, "-m", "pip", "install", "--upgrade", "pip"], timeout=300)
    log("installazione dipendenze (puo' richiedere diversi minuti)...")
    code, out = run([python, "-m", "pip", "install", "-r", str(REQ_FILE)], timeout=1800)
    print(out[-3000:])
    if code != 0:
        log("ERRORE pip: vedi output sopra. Rilancia lo script dopo aver sistemato.")
        return False
    log("dipendenze installate.")
    return True


def ollama_bin() -> str | None:
    return shutil.which("ollama")


def step_ollama() -> bool:
    exe = ollama_bin()
    if exe is None:
        log("ERRORE: 'ollama' non trovato nel PATH. Installalo da https://ollama.com/download e rilancia.")
        return False
    code, out = run([exe, "--version"])
    log(f"ollama: {out.splitlines()[0] if out else 'ok'}")
    code, out = run([exe, "list"])
    if code != 0:
        log("Ollama non risponde: avvialo (app Ollama o 'ollama serve') e rilancia. Dettaglio:")
        print(out[-1000:])
        return False
    if OLLAMA_MODEL in out:
        log(f"modello {OLLAMA_MODEL} gia' presente.")
        return True
    if not ask(f"scarico il modello locale {OLLAMA_MODEL} (~7 GB)?"):
        return False
    log(f"pull {OLLAMA_MODEL} in corso...")
    proc = subprocess.run([exe, "pull", OLLAMA_MODEL])
    if proc.returncode != 0:
        log(f"ERRORE pull {OLLAMA_MODEL}.")
        return False
    log(f"modello {OLLAMA_MODEL} pronto.")
    return True


def step_piper() -> bool:
    onnx = PIPER_DIR / (PIPER_VOICE.split("/")[-1] + ".onnx")
    cfg = PIPER_DIR / (PIPER_VOICE.split("/")[-1] + ".onnx.json")
    if onnx.exists() and cfg.exists():
        log(f"voce Piper gia' presente in {PIPER_DIR}.")
        return True
    if not ask(f"scarico la voce Piper italiana in {PIPER_DIR} (~60 MB)?"):
        return False
    PIPER_DIR.mkdir(parents=True, exist_ok=True)
    for url, dest in (
        (f"{PIPER_BASE}/{PIPER_VOICE}.onnx", onnx),
        (f"{PIPER_BASE}/{PIPER_VOICE}.onnx.json", cfg),
    ):
        log(f"download {url} ...")
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as exc:
            log(f"ERRORE download: {exc}")
            return False
    log("voce Piper pronta.")
    return True


def write_state(python: str) -> None:
    state = {
        "python": sys.version.split()[0],
        "venv_python": python,
        "requirements_sha256": file_hash(REQ_FILE) if REQ_FILE.exists() else "",
        "ollama_model": OLLAMA_MODEL,
    }
    try:
        VENV_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError as exc:
        log(f"AVVISO: impossibile scrivere {STATE_FILE}: {exc}")


def read_state() -> dict[str, object]:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def is_setup() -> bool:
    """Check veloce e non interattivo: True se venv + marker coerenti."""
    if not venv_python().exists() or not REQ_FILE.exists():
        return False
    state = read_state()
    return bool(state) and state.get("requirements_sha256") == file_hash(REQ_FILE)


def main(argv: list[str] | None = None) -> int:
    global ASSUME_YES
    parser = argparse.ArgumentParser(description="Setup venv condiviso + modelli locali.")
    parser.add_argument("--yes", "-y", action="store_true", help="accetta ogni download senza chiedere")
    parser.add_argument("--check-only", action="store_true", help="verifica soltanto, non installa nulla")
    parser.add_argument("--skip-ollama", action="store_true")
    parser.add_argument("--skip-piper", action="store_true")
    parser.add_argument("--skip-requirements", action="store_true")
    args = parser.parse_args(argv)
    ASSUME_YES = args.yes

    if args.check_only:
        ok = is_setup()
        log("ambiente OK" if ok else "ambiente NON configurato (lancia setup_env.py)")
        return 0 if ok else 1

    if not step_python():
        return 1
    if not step_venv():
        return 1
    python = target_python()
    ok = True
    if not args.skip_requirements:
        ok = step_requirements(python) and ok
    if not args.skip_ollama:
        ok = step_ollama() and ok
    if not args.skip_piper:
        ok = step_piper() and ok
    if ok:
        write_state(python)
        log("SETUP COMPLETATO. Usa il venv: "
            f"{VENV_DIR}\\Scripts\\activate  oppure direttamente {venv_python()}")
    else:
        log("SETUP INCOMPLETO: risolvi gli errori e rilancia (i passi gia' ok vengono saltati).")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
