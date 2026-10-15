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
REQ_FILE = SETUP_DIR / "requirements.txt"


def find_root() -> Path:
    """Trova la root del repo (quella con voice/ + backend/ + .env.example).

    Non usa un numero fisso di parents: funziona anche se la cartella setup/
    viene spostata o il repo ha un livello extra sopra.
    """
    for parent in [SETUP_DIR, *SETUP_DIR.parents]:
        if ((parent / "voice").is_dir() and (parent / "backend").is_dir()) or (
            (parent / ".env.example").is_file() and (parent / "setup").is_dir()
        ):
            return parent
    return SETUP_DIR.parent  # fallback: un livello sopra setup/


ROOT = find_root()
VENV_DIR = ROOT / ".venv"
STATE_FILE = VENV_DIR / ".setup_state.json"

MIN_PY = (3, 10)

# Modello locale servito da Ollama sul BE / macchina dedicata.
OLLAMA_MODEL = "gemma4:12b"

PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
PIPER_VOICE = "it/it_IT/riccardo/x_low/it_IT-riccardo-x_low"
PIPER_DIR = ROOT / "voice" / "models"

ASSUME_YES = False

# Pacchetti che richiedono compilazione C++ (es. webrtcvad su Windows senza
# Build Tools): se falliscono, il setup CONTINUA con warning. Voice usa
# EnergyVAD (default, zero-dep), quindi non sono bloccanti.
OPTIONAL_PKGS = {"webrtcvad", "webrtcvad-wheels"}


def banner(title: str) -> None:
    print(f"\n{'=' * 64}\n[setup] {title}\n{'=' * 64}", flush=True)


def log(msg: str) -> None:
    print(f"[setup] {msg}", flush=True)


def step(title: str, current: int, total: int) -> None:
    print(f"\n----- [{current}/{total}] {title} -----", flush=True)


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
    """Esegue un comando catturando l'output (per probe veloci)."""
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def run_live(cmd: list[str], timeout: int = 1800) -> int:
    """Esegue un comando mostrando l'output IN TEMPO REALE (stile installer).

    Ogni riga del sottoprocesso e' stampata subito con prefisso `|`.
    Ritorna l'exit code (un timeout uccide il processo e ritorna 124).
    """
    import time

    print(f"[setup] $ {' '.join(cmd)}", flush=True)
    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors="replace", bufsize=1,
        )
    except FileNotFoundError:
        print("[setup] comando non trovato.", flush=True)
        return 127
    assert proc.stdout is not None
    for line in proc.stdout:
        print(f"| {line.rstrip()}", flush=True)
    proc.wait(timeout=timeout)
    elapsed = time.monotonic() - start
    print(f"[setup] exit={proc.returncode} in {elapsed:.1f}s", flush=True)
    return proc.returncode


def download(url: str, dest: Path, timeout: int = 600) -> bool:
    """Download con barra di avanzamento testuale (MB scaricati / totali)."""
    import time

    print(f"[setup] download {url}", flush=True)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            total = int(resp.headers.get("Content-Length", "0") or 0)
            done = 0
            start = time.monotonic()
            last_pct = -1
            with open(dest, "wb") as fh:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    fh.write(chunk)
                    done += len(chunk)
                    if total > 0:
                        pct = int(done * 100 / total)
                        if pct // 5 != last_pct // 5:
                            last_pct = pct
                            mb = done / 1e6
                            tot = total / 1e6
                            print(f"| {pct:3d}%  {mb:.1f}/{tot:.1f} MB", flush=True)
            print(f"| completato: {done / 1e6:.1f} MB in {time.monotonic() - start:.1f}s -> {dest}", flush=True)
        return True
    except Exception as exc:
        print(f"[setup] ERRORE download: {exc}", flush=True)
        return False


def venv_python() -> Path:
    return VENV_DIR / "Scripts" / "python.exe"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def step_python() -> bool:
    log(
        f"interprete: {sys.version.split()[0]} (richiesto >= {'.'.join(map(str, MIN_PY))})")
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


def _pkg_name(requirement: str) -> str:
    """Nome pacchetto normalizzato da una riga di requirements (tollera versioni/extras)."""
    import re

    head = re.split(r"[<>=!~;\s\[]", requirement.strip(), maxsplit=1)[0]
    return head.strip().lower().replace("_", "-")


def parse_requirements() -> list[str]:
    """Righe utili di requirements.txt (senza commenti/vuoti)."""
    reqs: list[str] = []
    for line in REQ_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            reqs.append(line)
    return reqs


def step_requirements(python: str) -> tuple[bool, list[str]]:
    """Installa pacchetto per pacchetto con output live.

    Ritorna (core_ok, optional_failed): un pacchetto in OPTIONAL_PKGS puo'
    fallire (es. webrtcvad senza MSVC) senza bloccare il setup.
    """
    if not REQ_FILE.exists():
        log(f"ERRORE: {REQ_FILE} non trovato.")
        return False, []
    reqs = parse_requirements()
    log(f"{len(reqs)} pacchetti da {REQ_FILE.name} con {python}")
    if not ask("procedo con l'installazione (output live pacchetto per pacchetto)?"):
        return True, []
    log("upgrade pip...")
    if run_live([python, "-m", "pip", "install", "--upgrade", "pip"], timeout=300) != 0:
        log("AVVISO: upgrade pip fallito, continuo comunque.")
    optional_failed: list[str] = []
    core_failed: list[str] = []
    for i, req in enumerate(reqs, 1):
        name = _pkg_name(req)
        tag = "OPZIONALE" if name in OPTIONAL_PKGS else "richiesto"
        print(f"\n[setup] pacchetto {i}/{len(reqs)}: {req}  ({tag})", flush=True)
        code = run_live([python, "-m", "pip", "install", req], timeout=1200)
        if code == 0:
            print(f"[setup] ok: {name}", flush=True)
        elif name in OPTIONAL_PKGS:
            print(f"[setup] WARNING: '{name}' saltato (richiede compilatore C++; "
                  "Voice usa EnergyVAD di default: nessuna perdita di funzione).", flush=True)
            optional_failed.append(name)
        else:
            print(f"[setup] ERRORE su pacchetto richiesto: {name}", flush=True)
            core_failed.append(name)
    print("\n[setup] riepilogo pacchetti:", flush=True)
    print(f"| installati: {len(reqs) - len(core_failed) - len(optional_failed)}/{len(reqs)}", flush=True)
    if core_failed:
        print(f"| FALLITI (bloccanti): {', '.join(core_failed)}", flush=True)
    if optional_failed:
        print(f"| saltati (opzionali): {', '.join(optional_failed)}", flush=True)
    if core_failed:
        return False, optional_failed
    # Pacchetti locali del repo (voice/be/chat) installati editable nel venv condiviso,
    # cosi' `python -m voicebot` funziona dalla root senza PYTHONPATH.
    for pkg in ("voice", "be", "chat"):
        proj = ROOT / pkg / "pyproject.toml"
        if proj.exists():
            log(f"installazione editable ./{pkg} ...")
            code = run_live(
                [python, "-m", "pip", "install", "-e", str(proj.parent)], timeout=600)
            if code != 0:
                log(f"AVVISO: editable install ./{pkg} fallita (non fatale).")
    return True, optional_failed


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
    if not ask(f"scarico il modello locale {OLLAMA_MODEL} (~8 GB)?"):
        return False
    log(f"pull {OLLAMA_MODEL} in corso (output live di Ollama)...")
    if run_live([exe, "pull", OLLAMA_MODEL], timeout=3600) != 0:
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
        if not download(url, dest):
            return False
    log("voce Piper pronta.")
    return True


def write_state(python: str, optional_failed: list[str] | None = None) -> None:
    state = {
        "python": sys.version.split()[0],
        "venv_python": python,
        "requirements_sha256": file_hash(REQ_FILE) if REQ_FILE.exists() else "",
        "ollama_model": OLLAMA_MODEL,
        "optional_failed": optional_failed or [],
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
        if ok:
            missing = read_state().get("optional_failed", [])
            log("ambiente OK" + (f" (opzionali saltati: {missing})" if missing else ""))
        else:
            log("ambiente NON configurato (lancia setup_env.py)")
        return 0 if ok else 1

    banner(f"Setup ambiente condiviso  |  root={ROOT}  |  venv={VENV_DIR}")
    log(f"interprete di lancio: {sys.version.split()[0]}")
    # Guardia: tutto deve vivere dentro la repo (mai un .venv fuori progetto
    # come capitava con il vecchio calcolo del percorso).
    for marker in ("voice", "setup"):
        if not (ROOT / marker).is_dir():
            log(f"ERRORE: {ROOT} non sembra la root del repo (manca {marker}/). "
                "Sposto/copiato setup/? Interrompo per non creare file fuori posto.")
            return 1
    try:
        venv_inside = VENV_DIR.resolve().is_relative_to(ROOT.resolve())
    except AttributeError:  # Python < 3.9 (non atteso, fallback prudente)
        venv_inside = str(ROOT.resolve()) in str(VENV_DIR.resolve())
    if not venv_inside:
        log(f"ERRORE: il venv finirebbe fuori dalla repo ({VENV_DIR}). Interrompo.")
        return 1
    total_steps = 5
    step("Controllo interprete Python", 1, total_steps)
    if not step_python():
        return 1
    step("Creazione venv condiviso", 2, total_steps)
    if not step_venv():
        return 1
    python = target_python()
    log(f"python di destinazione: {python}")
    ok = True
    optional_failed: list[str] = []
    if not args.skip_requirements:
        step("Installazione dipendenze (output live)", 3, total_steps)
        req_ok, optional_failed = step_requirements(python)
        ok = req_ok and ok
    if not args.skip_ollama:
        step("Modello Ollama locale", 4, total_steps)
        ok = step_ollama() and ok
    if not args.skip_piper:
        step("Voce Piper locale (TTS)", 5, total_steps)
        ok = step_piper() and ok
    if ok:
        write_state(python, optional_failed)
        banner("SETUP COMPLETATO")
        log(f"attiva il venv: {VENV_DIR}\\Scripts\\activate")
        log(f"oppure lancia diretto: {venv_python()} -m voicebot")
        if optional_failed:
            log(f"nota: pacchetti opzionali saltati: {optional_failed} (non bloccanti)")
    else:
        log("SETUP INCOMPLETO: risolvi gli errori e rilancia (i passi gia' ok vengono saltati).")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
