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
OPTIONAL_PKGS = {"webrtcvad"}


def banner(title: str) -> None:
    print(f"\n{'=' * 64}\n[setup] {title}\n{'=' * 64}", flush=True)


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
    return step_spacy_model(python)


SPACY_MODEL = "it_core_news_md"


def step_spacy_model(python: str) -> bool:
    """Modello italiano di spaCy per il CHAT (anonimizzatore): non e' un pacchetto di requirements.txt, si scarica a parte."""
    code, _ = run([python, "-c", f"import spacy; spacy.load('{SPACY_MODEL}')"], timeout=180)
    if code == 0:
        good(f"modello spaCy {SPACY_MODEL} gia' presente.")
        return True
    info(f"scarico il modello italiano di spaCy ({SPACY_MODEL}, ~40 MB, serve al CHAT)...")
    code, out = run([python, "-m", "spacy", "download", SPACY_MODEL], timeout=900)
    if code != 0:
        print(_error_tail(out))
        bad(f"download del modello spaCy fallito: il CHAT non partirebbe. Riprova con: {python} -m spacy download {SPACY_MODEL}")
        return False
    good(f"modello spaCy {SPACY_MODEL} pronto.")
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
