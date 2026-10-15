"""Setup e avvio automatico di UNA macchina della LAN (solo stdlib, Windows).

Lo stesso script gira sulle 3 macchine: capisce da solo quale componente avviare.

Risoluzione ruolo (prima fonte valida vince):
  1. flag --role be|chat|voice
  2. variabile d'ambiente LAN_ROLE
  3. file lan/macchina.json (identita' di questa macchina: ruolo + IP auto-rilevato)
  4. file legacy lan/role.local.json
  5. domanda interattiva (poi salvata in macchina.json)

Prima esecuzione su una macchina: `machine_setup.py --sono` (o rispondi alla
domanda) -> da li' in poi tutto automatico, IP compreso.
`--pubblica-ip` scrive il proprio IP nel lan_config.json condiviso (solo se statici).

Flusso completo (default, senza flag):
  setup venv condiviso -> configura .env (IP del BE) -> firewall (istruzioni)
  -> avvia il componente in foreground (log live, Ctrl+C per fermare).

Altri modi:
  machine_setup.py --status                  verifica le 3 macchine via HTTP
  machine_setup.py --role voice --start       salta ai comandi
  machine_setup.py --write-launcher           crea AVVIA_<RUOLO>.bat
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

LAN_DIR = Path(__file__).resolve().parent
ROOT = LAN_DIR.parent
SETUP_DIR = ROOT / "setup"
CONFIG_FILE = LAN_DIR / "lan_config.json"
ROLE_FILE = LAN_DIR / "role.local.json"  # legacy, ancora letto come fallback
IDENTITY_FILE = LAN_DIR / "macchina.json"  # identità di QUESTA macchina (mai in git)
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"

ROLES = ("be", "chat", "voice")


def log(msg: str) -> None:
    print(f"[lan] {msg}", flush=True)


def load_config() -> dict[str, object]:
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def resolve_role(cli_role: str | None) -> str:
    """Ritorna be|chat|voice secondo l'ordine di priorita' documentato sopra."""
    if cli_role in ROLES:
        return cli_role
    env_role = os.environ.get("LAN_ROLE", "").strip().lower()
    if env_role in ROLES:
        log(f"ruolo da variabile LAN_ROLE={env_role}")
        return env_role
    for path in (IDENTITY_FILE, ROLE_FILE):
        try:
            saved = str(json.loads(path.read_text(encoding="utf-8")).get("role", "")).lower()
        except (OSError, ValueError):
            continue
        if saved in ROLES:
            log(f"ruolo da {path.name}: {saved}")
            return saved
    print("[lan] Questa macchina quale componente ospita?")
    for i, role in enumerate(ROLES, 1):
        print(f"  {i}. {role}")
    while True:
        try:
            choice = input("[lan] numero [1-3]: ").strip()
        except EOFError:
            choice = ""
        mapping = {"1": "be", "2": "chat", "3": "voice", "be": "be", "chat": "chat", "voice": "voice"}
        if choice in mapping:
            role = mapping[choice]
            ROLE_FILE.write_text(json.dumps({"role": role}, indent=2), encoding="utf-8")
            log(f"ruolo salvato in lan/{ROLE_FILE.name} (file locale, non committare)")
            return role
        print("[lan] scelta non valida.")


def get_own_ip() -> str:
    """Rileva l'IP LAN di QUESTA macchina (solo stdlib, nessun traffico inviato).

    Strategia: socket UDP "connesso" (nessun pacchetto parte) verso gateway
    tipici per capire quale interfaccia uscirebbe; fallback su hostname.
    Scarta loopback e link-local. Ritorna "" se non rilevabile.
    """
    import socket

    candidates: list[str] = []
    for target in ("8.8.8.8", "192.168.1.1", "10.0.0.1"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect((target, 80))
            candidates.append(str(sock.getsockname()[0]))
        except OSError:
            pass
        finally:
            sock.close()
    try:
        _, _, addrs = socket.gethostbyname_ex(socket.gethostname())
        candidates.extend(addrs)
    except OSError:
        pass
    for ip in candidates:
        if ip.startswith("127.") or ip.startswith("169.254.") or ":" in ip:
            continue
        return ip
    return ""


def load_identity() -> dict[str, str]:
    try:
        data = json.loads(IDENTITY_FILE.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_identity(identity: dict[str, str]) -> None:
    IDENTITY_FILE.write_text(json.dumps(identity, indent=2), encoding="utf-8")


def ensure_identity(role: str) -> dict[str, str]:
    """Crea/aggiorna lan/macchina.json: ruolo + IP auto-rilevato (+ nome opzionale).

    Prima esecuzione: chiede 'chi sei' (se ruolo non noto) e propone l'IP rilevato
    (invio = conferma, oppure digitazione manuale). Poi tutto e' automatico.
    """
    identity = load_identity()
    changed = False
    if identity.get("role") != role:
        identity["role"] = role
        changed = True
    detected = get_own_ip()
    if not identity.get("host") or identity.get("host") != detected:
        if detected and sys.stdin.isatty() and not ASSUME_IP:
            try:
                answer = input(f"[lan] IP di questa macchina [{detected}]: ").strip()
                identity["host"] = answer or detected
            except EOFError:
                identity["host"] = detected
        else:
            identity["host"] = detected or identity.get("host", "")
        changed = True
    if "nome" not in identity and sys.stdin.isatty() and not ASSUME_IP:
        try:
            nome = input("[lan] nome macchina (es. PC-BE, facoltativo) []: ").strip()
            if nome:
                identity["nome"] = nome
                changed = True
        except EOFError:
            pass
    if changed:
        save_identity(identity)
        log(f"identita' salvata in lan/{IDENTITY_FILE.name}: {identity}")
    else:
        log(f"identita' nota: {identity}")
    return identity


ASSUME_IP = False


def effective_hosts(config: dict[str, object], identity: dict[str, str]) -> dict[str, str]:
    """Mappa ruolo -> host EFFETTIVO: per il proprio ruolo vale l'IP auto-rilevato."""
    hosts: dict[str, str] = {}
    for role in ROLES:
        node = config[role]
        assert isinstance(node, dict)
        hosts[role] = str(node.get("host", ""))
    if identity.get("role") in ROLES and identity.get("host"):
        hosts[identity["role"]] = identity["host"]
    return hosts


def publish_ip(config: dict[str, object], identity: dict[str, str]) -> bool:
    """Scrive l'IP rilevato nel lan_config.json CONDIVISO (opt-in esplicito).

    Utile una tantum per fissare IP statici; con DHCP meglio di no (vedi README).
    """
    role = identity.get("role", "")
    host = identity.get("host", "")
    if role not in ROLES or not host:
        log("ERRORE: identità incompleta, niente da pubblicare.")
        return False
    node = config[role]
    assert isinstance(node, dict)
    node["host"] = host
    CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"pubblicato in lan_config.json: {role}.host = {host} (da committare con git)")
    return True


def ensure_repo_root() -> bool:
    for marker in ("voice", "backend", "chat", "setup"):
        if not (ROOT / marker).is_dir():
            log(f"ERRORE: {ROOT} non e' la root del repo (manca {marker}/).")
            return False
    return True


def step_setup_env() -> bool:
    """Riusa il setup condiviso: se il venv non e' pronto lo crea (interattivo)."""
    sys.path.insert(0, str(SETUP_DIR))
    from env_check import ensure_environment

    log("controllo venv condiviso (setup/)...")
    if ensure_environment():
        return True
    log("setup non completato: riavvia questo script dopo aver sistemato.")
    return False


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                values[key.strip()] = val.strip()
    return values


def configure_env(role: str, config: dict[str, object], be_host: str | None) -> bool:
    """Scrive/aggiorna il .env di QUESTA macchina (mai committato).

    - tutte le macchine: BACKEND_BASE_URL=http://<IP-BE>:8000, HOST=0.0.0.0
    - BE_URL per la chat (letto da chat/app.py).
    """
    be = config["be"]
    assert isinstance(be, dict)
    ident = load_identity()
    host = be_host or ident.get("be_host") or str(be.get("host", "192.168.1.10"))
    port = int(be.get("port", 8000))
    if be_host is None and not ident.get("be_host") and sys.stdin.isatty():
        try:
            answer = input(f"[lan] IP LAN della macchina BE [{host}]: ").strip()
            if answer:
                host = answer
        except EOFError:
            pass
    if ident.get("be_host") != host:
        ident["be_host"] = host
        save_identity(ident)
        log(f"IP BE ricordato in lan/{IDENTITY_FILE.name} (non servira' richiederlo)")
    values = read_env()
    values["HOST"] = "0.0.0.0"
    values["BACKEND_BASE_URL"] = f"http://{host}:{port}"
    values["BE_URL"] = f"http://{host}:{port}"
    if role == "be":
        values.setdefault("PORT", str(port))
        values.setdefault("OLLAMA_MODEL", str(config.get("ollama_model", "gemma4:12b")))
    if not ENV_EXAMPLE.is_file():
        log(f"ERRORE: manca {ENV_EXAMPLE} (serve come base).")
        return False
    header = [l for l in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines() if l.startswith("#")]
    lines = [f"# .env generato da lan/machine_setup.py per ruolo={role} (NON committare)"]
    lines += header[:3]
    for key in sorted(values):
        lines.append(f"{key}={values[key]}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f".env scritto per ruolo={role}: BACKEND_BASE_URL={values['BACKEND_BASE_URL']}")
    return True


def firewall_hint(role: str, config: dict[str, object]) -> None:
    """Stampa (e prova) le regole firewall Windows per la porta del ruolo."""
    node = config[role]
    assert isinstance(node, dict)
    port = int(node.get("port", 0))
    rule = f"AI4R-{role}-{port}"
    cmd = (f'netsh advfirewall firewall add rule name="{rule}" '
           f'dir=in action=allow protocol=TCP localport={port}')
    print(f"[lan] firewall: serve la porta {port}/TCP in ingresso. Comando da admin:")
    print(f"      {cmd}")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, shell=True)
        if proc.returncode == 0:
            log("regola firewall applicata.")
        else:
            log("regola NON applicata (serve prompt amministratore): eseguila a mano.")
    except Exception as exc:
        log(f"regola NON applicata ({exc}): eseguila a mano da admin.")


def wait_for_be(timeout_s: int = 180) -> bool:
    """Le macchine CHAT/VOICE attendono il BE (fulcro) prima di avviarsi.

    Polla <BACKEND_BASE_URL>/.env ogni 2 s. Ritorna False su timeout/Ctrl+C.
    """
    from urllib.parse import urlparse

    base = read_env().get("BACKEND_BASE_URL", "http://192.168.1.10:8000").rstrip("/")
    host = urlparse(base).netloc or base
    log(f"attendo il BE su {base} (accendi la macchina BE; Ctrl+C per saltare l'attesa)...")
    deadline = time.monotonic() + timeout_s
    attempt = 0
    last_detail = ""
    while time.monotonic() < deadline:
        attempt += 1
        for path in ("/api/health", "/health"):
            status, detail = check_one("be", base, path, timeout=4)
            last_detail = detail
            if status == "OK":
                log(f"BE raggiungibile ({detail}).")
                return True
        if attempt % 5 == 0:
            log(f"BE non ancora su ({last_detail}). Riprovo... ({attempt * 2}s trascorsi)")
        try:
            time.sleep(2)
        except KeyboardInterrupt:
            log("attesa interrotta: avvio comunque (il componente riprovera' da solo).")
            return True
    log(f"TIMEOUT {timeout_s}s: BE non raggiungibile ({last_detail}).")
    return False


def start_component(role: str, config: dict[str, object]) -> int:
    """Avvia il componente in foreground con log live (Ctrl+C ferma)."""
    node = config[role]
    assert isinstance(node, dict)
    start = node["start"]
    assert isinstance(start, dict)
    argv = [str(a) for a in start["argv"]]
    # .venv/Scripts/python.exe relativo alla root (portabile tra macchine).
    if argv[0].startswith(".venv"):
        argv[0] = str(ROOT / argv[0].replace("/", os.sep))
    cwd = ROOT / str(start.get("cwd", "."))
    env = os.environ.copy()
    for key, val in dict(start.get("env", {})).items():
        env.setdefault(key, str(val).replace("192.168.1.10",
                      read_env().get("BACKEND_BASE_URL", "http://192.168.1.10:8000").split("://")[1].split(":")[0]))
    log(f"avvio {role}: {' '.join(argv)}  (cwd={cwd}, Ctrl+C per fermare)")
    try:
        proc = subprocess.Popen(argv, cwd=str(cwd), env=env)
        return proc.wait()
    except KeyboardInterrupt:
        log("arresto richiesto, fermo il componente...")
        try:
            proc.terminate()
            proc.wait(timeout=15)
        except Exception:
            proc.kill()
        return 0
    except FileNotFoundError:
        log(f"ERRORE: {argv[0]} non trovato: il venv non e' pronto, rilancia senza --start.")
        return 1


def check_one(name: str, base: str, path: str, timeout: int = 5) -> tuple[str, str]:
    url = base.rstrip("/") + path
    start = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            ms = int((time.monotonic() - start) * 1000)
            ok = 200 <= resp.status < 300
            return ("OK", f"{resp.status} in {ms}ms") if ok else ("KO", f"HTTP {resp.status}")
    except Exception as exc:
        return ("KO", f"{type(exc).__name__}: {exc}")


def cmd_status(
    config: dict[str, object],
    be_override: str | None = None,
    identity: dict[str, str] | None = None,
) -> int:
    """Ping HTTP alle 3 macchine e stampa la tabella di stato LAN.

    Se stessi via 127.0.0.1 (il componente locale deve rispondere in locale),
    il BE via IP ricordato/flag/config, gli altri via lan_config.json.
    """
    identity = identity or {}
    own = identity.get("role", "")
    hosts = effective_hosts(config, identity)
    print("\n[lan] stato LAN:")
    print(f"{'ruolo':<7} {'indirizzo':<28} {'stato':<5} dettaglio")
    all_ok = True
    for role in ROLES:
        node = config[role]
        assert isinstance(node, dict)
        if role == "be":
            host = be_override or identity.get("be_host") or hosts["be"]
        elif role == own:
            host = "127.0.0.1"
        else:
            host = hosts[role]
        base = f"http://{host}:{int(node.get('port', 0))}"
        status, detail = check_one(role, base, str(node.get("health", "/health")))
        all_ok = all_ok and status == "OK"
        print(f"{role:<7} {base:<28} {status:<5} {detail}")
    print("[lan] TUTTO OK" if all_ok else "[lan] qualcosa non risponde: vedi dettaglio sopra")
    return 0 if all_ok else 1


def cmd_show(config: dict[str, object], identity: dict[str, str]) -> int:
    """Mostra chi sono io e chi sono gli altri (mappa effettiva)."""
    hosts = effective_hosts(config, identity)
    print("\n[lan] mappa effettiva:")
    for role in ROLES:
        node = config[role]
        assert isinstance(node, dict)
        tag = "  <-- QUESTA MACCHINA" if role == identity.get("role") else ""
        print(f"  {role:<6} {hosts[role]:<16} :{node.get('port')}{tag}")
    print(f"  BE per .env: {identity.get('be_host', hosts['be'])}")
    return 0


def cmd_write_launcher(role: str) -> int:
    """Crea AVVIA_<RUOLO>.bat (doppio click per avviare senza terminale esperto)."""
    bat = ROOT / f"AVVIA_{role.upper()}.bat"
    bat.write_text(
        "@echo off\r\n"
        f'title AI4R {role}\r\n'
        "cd /d %~dp0\r\n"
        f".venv\\Scripts\\python.exe lan\\machine_setup.py --role {role} --start\r\n"
        "pause\r\n",
        encoding="utf-8",
    )
    log(f"launcher creato: {bat.name} (doppio click per avviare {role})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Setup/avvio di una macchina LAN (be|chat|voice).")
    parser.add_argument("--role", choices=list(ROLES), help="forza il ruolo (altrimenti auto)")
    parser.add_argument("--be-host", default=None, help="IP LAN del BE (altrimenti lan_config.json/domanda)")
    parser.add_argument("--start", action="store_true", help="avvia e basta (salta check/configure)")
    parser.add_argument("--configure-only", action="store_true", help="solo .env, senza avviare")
    parser.add_argument("--status", action="store_true", help="ping HTTP alle 3 macchine ed esci")
    parser.add_argument("--write-launcher", action="store_true", help="crea AVVIA_<RUOLO>.bat ed esci")
    parser.add_argument("--no-wait", action="store_true",
                        help="chat/voice: non attendere il BE prima di avviare")
    parser.add_argument("--wait-timeout", type=int, default=180,
                        help="secondi max di attesa BE (default 180)")
    parser.add_argument("--sono", action="store_true",
                        help="identifica questa macchina (ruolo+IP) senza domande e senza avviare")
    parser.add_argument("--mostra-identita", action="store_true",
                        help="mostra chi sono io e gli altri (mappa effettiva) ed esci")
    parser.add_argument("--pubblica-ip", action="store_true",
                        help="scrive il mio IP nel lan_config.json condiviso (solo IP statici!) ed esci")
    args = parser.parse_args(argv)
    global ASSUME_IP

    config = load_config()
    if args.status:
        return cmd_status(config, args.be_host, load_identity())
    if not ensure_repo_root():
        return 1
    role = resolve_role(args.role)
    if args.sono:
        ASSUME_IP = True
    identity = ensure_identity(role)
    if args.sono or args.mostra_identita:
        return cmd_show(config, identity)
    if args.pubblica_ip:
        return 0 if publish_ip(config, identity) else 1
    if args.write_launcher:
        return cmd_write_launcher(role)
    if not args.start:
        if not step_setup_env():
            return 1
        if not configure_env(role, config, args.be_host):
            return 1
        firewall_hint(role, config)
        if args.configure_only:
            return 0
    if role in ("chat", "voice") and not args.no_wait:
        if not wait_for_be(timeout_s=args.wait_timeout):
            log("BE assente: componente NON avviato. Accendi il BE e rilancia (o --no-wait).")
            return 1
    return start_component(role, config)


if __name__ == "__main__":
    raise SystemExit(main())
