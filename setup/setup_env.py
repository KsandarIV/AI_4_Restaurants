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
import time
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


TOTAL_STEPS = 5


def log(msg: str) -> None:
    print(f"[setup] {msg}", flush=True)


def header(n: int, title: str) -> None:
    """Intestazione ben visibile di un passo (es. [2/5] Ambiente virtuale)."""
    print(f"\n=== [{n}/{TOTAL_STEPS}] {title} ===", flush=True)


def info(msg: str) -> None:
    print(f"  ..  {msg}", flush=True)


def good(msg: str) -> None:
    print(f"  OK  {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"  !!  {msg}", flush=True)


def bad(msg: str) -> None:
    print(f"  XX  {msg}", flush=True)


def ask(question: str, default_yes: bool = True) -> bool:
    """Conferma interattiva per ogni passo (saltata con --yes)."""
    if ASSUME_YES:
        return True
    suffix = "[S/n]" if default_yes else "[s/N]"
    try:
        answer = input(f"  ??  {question} {suffix} ").strip().lower()
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
    header(1, "Python")
    info(f"versione trovata: {sys.version.split()[0]} (minimo richiesto: {'.'.join(map(str, MIN_PY))})")
    if sys.version_info < MIN_PY:
        bad("Python troppo vecchio: installa Python 3.11 o 3.12.")
        return False
    if sys.version_info >= (3, 13):
        warn("Python 3.13+: alcuni pacchetti potrebbero non avere ancora i file "
             "precompilati. Se l'installazione fallisce, usa Python 3.11 o 3.12.")
    good("versione di Python adatta.")
    return True


def step_venv() -> bool:
    header(2, "Ambiente virtuale (.venv condiviso da BE, CHAT, VOICE)")
    py = venv_python()
    if py.exists():
        good(f"gia' presente: {VENV_DIR}")
        return True
    if not ask(f"creo il venv in {VENV_DIR}?"):
        warn("venv saltato: i passi successivi useranno il Python corrente.")
        return False
    info("creazione in corso (puo' richiedere un minuto)...")
    code, out = run([sys.executable, "-m", "venv", str(VENV_DIR)], timeout=300)
    if code != 0 or not py.exists():
        bad(f"creazione del venv fallita:\n{out}")
        return False
    good("venv creato.")
    return True


def target_python() -> str:
    py = venv_python()
    return str(py) if py.exists() else sys.executable


def step_requirements(python: str) -> bool:
    header(3, "Dipendenze Python (requirements.txt)")
    if not REQ_FILE.exists():
        bad(f"{REQ_FILE} non trovato.")
        return False
    if not ask(f"installo {REQ_FILE.name} nel venv?"):
        warn("installazione dipendenze saltata.")
        return True
    info("aggiorno pip...")
    run([python, "-m", "pip", "install", "--upgrade", "pip"], timeout=300)
    info("installo i pacchetti (puo' richiedere diversi minuti, nessun output fino alla fine)...")
    start = time.time()
    code, out = run([python, "-m", "pip", "install", "--progress-bar", "off",
                    "-r", str(REQ_FILE)], timeout=1800)
    elapsed = int(time.time() - start)
    if code != 0:
        print(_error_tail(out))
        bad(f"installazione fallita dopo {elapsed}s.")
        _pip_hint(out)
        info("Sistema il problema e rilancia lo script: i passi gia' riusciti vengono saltati.")
        return False
    installed = [ln for ln in out.splitlines() if ln.startswith("Successfully installed")]
    n_new = len(installed[0].split()) - 2 if installed else 0
    if n_new:
        good(f"{n_new} pacchetti installati in {elapsed}s.")
    else:
        good(f"tutti i pacchetti erano gia' aggiornati ({elapsed}s).")
    # Pacchetti locali del repo (voice/be/chat) installati editable nel venv condiviso,
    # cosi' `python -m voicebot` funziona dalla root senza PYTHONPATH.
    for pkg in ("voice", "be", "chat"):
        proj = ROOT / pkg / "pyproject.toml"
        if proj.exists():
            info(f"installo il progetto locale ./{pkg} (editable)...")
            code, out = run([python, "-m", "pip", "install",
                            "-e", str(proj.parent)], timeout=600)
            if code != 0:
                warn(f"installazione di ./{pkg} fallita (non bloccante):\n{out[-1000:]}")
            else:
                good(f"./{pkg} installato.")
    return True


def _error_tail(out: str) -> str:
    """Solo la parte utile dell'output pip: righe 'error' e coda, non tutto il log."""
    lines = out.splitlines()
    key = [ln for ln in lines if "error" in ln.lower() or "ERROR" in ln]
    return "\n".join(["--- dettaglio errore pip ---", *key[-8:], "----------------------------"])


def _pip_hint(out: str) -> None:
    """Spiega in italiano le cause piu' comuni dei fallimenti di pip."""
    low = out.lower()
    if "visual c++" in low or "microsoft c++ build tools" in low:
        warn("Un pacchetto va compilato ma manca il compilatore C++ di Microsoft.")
        info("Soluzione: usa Python 3.11/3.12 (hanno i file precompilati) oppure installa "
             "'Build Tools per Visual Studio' (carico C++).")
    elif "no matching distribution" in low or "could not find a version" in low:
        warn("Nessuna versione di un pacchetto e' compatibile con questo Python.")
        info("Soluzione: ricrea il venv con Python 3.11 o 3.12.")
    elif "connection" in low or "timed out" in low or "network" in low:
        warn("Problema di rete durante il download: controlla la connessione e riprova.")


def ollama_bin() -> str | None:
    return shutil.which("ollama")


def step_ollama() -> bool:
    header(4, f"Ollama e modello linguistico locale ({OLLAMA_MODEL})")
    exe = ollama_bin()
    if exe is None:
        bad("'ollama' non trovato nel PATH.")
        info("Installalo da https://ollama.com/download e rilancia.")
        return False
    code, out = run([exe, "--version"])
    good(f"Ollama installato ({out.splitlines()[0] if out else 'versione sconosciuta'}).")
    code, out = run([exe, "list"])
    if code != 0:
        bad("Ollama non risponde: avvia l'app Ollama (o 'ollama serve') e rilancia.")
        print(out[-1000:])
        return False
    if OLLAMA_MODEL in out:
        good(f"modello {OLLAMA_MODEL} gia' scaricato.")
        return True
    warn(f"il modello {OLLAMA_MODEL} non e' ancora scaricato.")
    if not ask(f"scarico {OLLAMA_MODEL} (~7 GB, serve per il BE)?"):
        warn("modello NON scaricato: il BE non potra' rispondere finche' non lo scarichi "
             f"(oppure: 'ollama pull {OLLAMA_MODEL}'). Per ignorare questo passo: --skip-ollama.")
        return False
    info("download in corso (vedrai l'avanzamento di Ollama)...")
    proc = subprocess.run([exe, "pull", OLLAMA_MODEL])
    if proc.returncode != 0:
        bad(f"download di {OLLAMA_MODEL} fallito.")
        return False
    good(f"modello {OLLAMA_MODEL} pronto.")
    return True


def step_piper() -> bool:
    onnx = PIPER_DIR / (PIPER_VOICE.split("/")[-1] + ".onnx")
    cfg = PIPER_DIR / (PIPER_VOICE.split("/")[-1] + ".onnx.json")
    header(5, "Voce italiana Piper (sintesi vocale del VOICE)")
    if onnx.exists() and cfg.exists():
        good(f"gia' presente in {PIPER_DIR}.")
        return True
    if not ask(f"scarico la voce Piper italiana in {PIPER_DIR} (~60 MB)?"):
        warn("voce NON scaricata: il VOICE non potra' parlare. Per ignorare: --skip-piper.")
        return False
    PIPER_DIR.mkdir(parents=True, exist_ok=True)
    for url, dest in (
        (f"{PIPER_BASE}/{PIPER_VOICE}.onnx", onnx),
        (f"{PIPER_BASE}/{PIPER_VOICE}.onnx.json", cfg),
    ):
        info(f"scarico {dest.name} ...")
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as exc:
            bad(f"download fallito: {exc}")
            return False
    good("voce Piper pronta.")
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
    parser = argparse.ArgumentParser(
        description="Setup venv condiviso + modelli locali.")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="accetta ogni download senza chiedere")
    parser.add_argument("--check-only", action="store_true",
                        help="verifica soltanto, non installa nulla")
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
    results: list[tuple[str, str]] = []  # (nome passo, esito)
    for name, skip, fn in (
        ("Dipendenze Python", args.skip_requirements, lambda: step_requirements(python)),
        ("Ollama + modello", args.skip_ollama, step_ollama),
        ("Voce Piper", args.skip_piper, step_piper),
    ):
        if skip:
            results.append((name, "saltato (opzione --skip)"))
        else:
            results.append((name, "OK" if fn() else "DA SISTEMARE"))

    ok = all(r != "DA SISTEMARE" for _, r in results)
    print("\n=== RIEPILOGO ===")
    for name, res in results:
        mark = "XX" if res == "DA SISTEMARE" else ("OK" if res == "OK" else "--")
        print(f"  {mark}  {name}: {res}")
    print()
    if ok:
        write_state(python)
        log("SETUP COMPLETATO. Attiva il venv con: "
            f"{VENV_DIR}\\Scripts\\activate")
    else:
        log("SETUP INCOMPLETO: sistema i punti 'DA SISTEMARE' qui sopra e rilancia "
            "(i passi gia' riusciti vengono saltati).")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
