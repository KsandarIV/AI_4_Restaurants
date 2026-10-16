"""Starts the demo sites of a machine and opens them in the browser (called by lan/machine_setup.py).

Topology: a STAR with the BE in the middle. CHAT and VOICE never talk to each other; everything the complete site needs
goes through the gateway that runs on the BE (``showcase/gateway.py``).

    BE      starts the gateway   https://completo.localhost:8090  (also https://<BE-IP>:8090)   + solo-be.localhost:8080
    CHAT    opens                https://<BE-IP>:8090                                            + chat.localhost:8080
    VOICE   opens                https://<BE-IP>:8090                                            + voce.localhost:8003/test-voice

``*.localhost`` always means "this PC" and is a secure context; the gateway's HTTPS gives the CHAT and VOICE PCs a secure
context too (microphone). The first visit shows a certificate warning (self-signed): accept it once per browser.

Every machine opens its own test page AND the complete site. AI4R_NO_BROWSER=1 starts everything without opening tabs.
"""

from __future__ import annotations

import json
import os
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from showcase import peers

GATEWAY_PORT = 8090
FRONTEND_PORT = 8080
VOICE_PORT = 8003
GATEWAY_VERSION = 3  # must match showcase/gateway.py: an older server left on the port is reported, not trusted

_UNVERIFIED = ssl.create_default_context()  # the gateway is self-signed: for a *health probe* we only need it to answer
_UNVERIFIED.check_hostname = False
_UNVERIFIED.verify_mode = ssl.CERT_NONE


def names(role: str, be_host: str) -> dict[str, str]:
    """Page addresses for ``role``. The complete site is on the BE: loopback there, ``https://<BE-IP>`` elsewhere."""
    complete = (f"https://completo.localhost:{GATEWAY_PORT}/" if role == "be"
                else f"https://{be_host or '<IP-BE>'}:{GATEWAY_PORT}/")
    return {
        "solo-be": f"http://solo-be.localhost:{FRONTEND_PORT}/",
        "completo": complete,
        "chat": f"http://chat.localhost:{FRONTEND_PORT}/",
        "voce": f"http://voce.localhost:{VOICE_PORT}/test-voice",
    }


def probes(role: str, be_host: str) -> dict[str, str]:
    """URLs that answer when the page behind each name is ready."""
    gateway = f"https://{'127.0.0.1' if role == 'be' else (be_host or '127.0.0.1')}:{GATEWAY_PORT}/health"
    return {"solo-be": f"http://127.0.0.1:{FRONTEND_PORT}/", "completo": gateway,
            "chat": f"http://127.0.0.1:{FRONTEND_PORT}/", "voce": f"http://127.0.0.1:{VOICE_PORT}/health"}


NAMES = names("be", "")  # kept for documentation and tests: the BE's view
# Pages opened automatically per role: its own test page + the complete site.
OPEN = {"be": ["solo-be", "completo"], "chat": ["chat", "completo"], "voice": ["voce", "completo"]}


def log(msg: str) -> None:
    """Prefixed console line."""
    print(f"[showcase] {msg}", flush=True)


def _fetch(url: str, timeout: float = 2.0) -> bytes:
    context = _UNVERIFIED if url.startswith("https") else None
    with urllib.request.urlopen(url, timeout=timeout, context=context) as resp:  # noqa: S310
        return bytes(resp.read(65536))


def _port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _gateway_is_current() -> bool:
    """Is the server already on the gateway port our current gateway? (a stale one would keep old behaviour)"""
    for scheme in ("https", "http"):
        try:
            data = json.loads(_fetch(f"{scheme}://127.0.0.1:{GATEWAY_PORT}/health"))
            return bool(data.get("gateway")) and int(data.get("version", 0)) >= GATEWAY_VERSION
        except Exception:  # noqa: BLE001
            continue
    return False


def _wait_and_open(pages: list[str], urls: dict[str, str], probe_urls: dict[str, str], timeout_s: int = 300) -> None:
    """Open each page as soon as its server answers (voice may need time to load the models)."""
    pending = list(pages)
    deadline = time.monotonic() + timeout_s
    while pending and time.monotonic() < deadline:
        for key in list(pending):
            try:
                _fetch(probe_urls[key])
            except Exception:  # noqa: BLE001 - not up yet
                continue
            pending.remove(key)
            webbrowser.open(urls[key])
        time.sleep(1.5)
    for key in pending:
        log(f"ATTENZIONE: {urls[key]} non ha risposto entro {timeout_s}s (servizio spento o porta occupata da un vecchio processo?)")


def _discover_in_background(own_ip: str, be_host: str) -> None:
    """BE only: find (and cache) the VOICE and CHAT PCs while everything boots; the gateway reads the result lazily."""
    for role in ("voice", "chat"):
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            host = peers.resolve(role, own_role="be", own_ip=own_ip, be_host=be_host, allow_scan=True)
            if host:
                log(f"PC {role}: {host} (verificato)")
                break
            time.sleep(10)  # that PC may simply not be up yet


def start_showcase(role: str, root: Path, hosts: dict[str, str]) -> list["subprocess.Popen[bytes]"]:
    """Start the extra servers of ``role`` and schedule the browser tabs. Returns processes to clean up."""
    venv_python = root / ".venv" / "Scripts" / "python.exe"
    exe = str(venv_python) if venv_python.exists() else sys.executable
    procs: list[subprocess.Popen[bytes]] = []
    own_ip = peers._own_ip()
    be_host = peers._be_host_from_env() or hosts.get("be", "")
    urls = names(role, be_host)

    if role == "be":
        if _port_busy(GATEWAY_PORT):
            if not _gateway_is_current():
                log(f"ATTENZIONE: sulla porta {GATEWAY_PORT} gira un vecchio server (versione precedente o avviato a mano). "
                    f"Chiudilo: Get-NetTCPConnection -LocalPort {GATEWAY_PORT} -State Listen | % "
                    "{ Stop-Process -Id $_.OwningProcess -Force }")
        else:
            procs.append(subprocess.Popen([exe, str(root / "showcase" / "gateway.py"), "--port", str(GATEWAY_PORT)],
                                          cwd=str(root)))
        threading.Thread(target=_discover_in_background, args=(own_ip, be_host), daemon=True).start()
    if role == "chat":
        if _port_busy(FRONTEND_PORT):
            log(f"porta {FRONTEND_PORT} gia' occupata: se non e' il sito di frontend/ aggiornato, chiudi il processo vecchio")
        else:  # the chat colleague's own page, automatic
            procs.append(subprocess.Popen([exe, "-m", "http.server", str(FRONTEND_PORT), "--directory", "frontend"],
                                          cwd=str(root)))

    log("pagine di questa macchina (indirizzi facili da ricordare):")
    mine = OPEN.get(role, [])
    for key in mine:
        log(f"   {key:<9} {urls[key]}")
    if role != "be":
        log("il sito completo e' sul BE (certificato autofirmato: al primo accesso 'Avanzate' -> 'Procedi')")
    log("elenco completo dei siti: docs/SITI.md")
    if os.environ.get("AI4R_NO_BROWSER") != "1":
        threading.Thread(target=_wait_and_open, args=(mine, urls, probes(role, be_host)), daemon=True).start()
    return procs
