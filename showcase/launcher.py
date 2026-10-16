"""Starts the demo sites of a machine and opens them in the browser (called by lan/machine_setup.py).

Easy addresses (``*.localhost`` always means "this PC" and counts as a secure page: the microphone works):

    solo-be.localhost:8080          the site WITHOUT working chat/voice (they appear bottom-right)        [BE]
    chat.localhost:8080             the chat colleague's own site (frontend/), chat working              [CHAT]
    voce.localhost:8003/test-voice  the voice test page: orb + STATO / TECNICA tabs                      [VOICE]
    completo.localhost:8090         the COMPLETE site: chat + voice + staff area across the three PCs    [all]

Every machine opens its own test page AND the complete site. Set AI4R_NO_BROWSER=1 to start without opening tabs.

Peer addresses (the voice PC for the complete site, the chat PC for the voice server's chat window) are never taken
on trust from ``lan/lan_config.json``: see ``showcase.peers`` (verified, cached, rediscovered).
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from showcase import peers

SHOWCASE_PORT = 8090
FRONTEND_PORT = 8080
VOICE_PORT = 8003
SERVE_VERSION = 2  # must match showcase/serve.py: an older server left running is reported, not trusted

NAMES = {
    "solo-be": f"http://solo-be.localhost:{FRONTEND_PORT}/",
    "completo": f"http://completo.localhost:{SHOWCASE_PORT}/",
    "chat": f"http://chat.localhost:{FRONTEND_PORT}/",
    "voce": f"http://voce.localhost:{VOICE_PORT}/test-voice",
}
PROBES = {
    "solo-be": f"http://127.0.0.1:{FRONTEND_PORT}/",
    "completo": f"http://127.0.0.1:{SHOWCASE_PORT}/health",
    "chat": f"http://127.0.0.1:{FRONTEND_PORT}/",
    "voce": f"http://127.0.0.1:{VOICE_PORT}/health",
}
# Pages opened automatically per role: its own test page + the complete site.
OPEN = {"be": ["solo-be", "completo"], "chat": ["chat", "completo"], "voice": ["voce", "completo"]}


def log(msg: str) -> None:
    """Prefixed console line."""
    print(f"[showcase] {msg}", flush=True)


def _port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _showcase_is_current() -> bool:
    """Is the server already on 8090 ours and up to date? (a stale one would keep serving old behaviour)"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{SHOWCASE_PORT}/health", timeout=2) as resp:
            return int(json.loads(resp.read()).get("version", 0)) >= SERVE_VERSION
    except Exception:  # noqa: BLE001
        return False


def _wait_and_open(pages: list[str], timeout_s: int = 300) -> None:
    """Open each page as soon as its server answers (voice may need time to load the models)."""
    pending = list(pages)
    deadline = time.monotonic() + timeout_s
    while pending and time.monotonic() < deadline:
        for key in list(pending):
            try:
                urllib.request.urlopen(PROBES[key], timeout=2).close()
            except Exception:  # noqa: BLE001 - not up yet
                continue
            pending.remove(key)
            webbrowser.open(NAMES[key])
        time.sleep(1.5)
    for key in pending:
        log(f"ATTENZIONE: {NAMES[key]} non ha risposto entro {timeout_s}s (porta occupata da un vecchio processo?)")


def _discover_in_background(own_role: str, own_ip: str, be_host: str) -> None:
    """Find (and cache) the peers while the component boots; the servers read the result lazily."""
    for role in ("voice", "chat"):
        if role == own_role:
            continue
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            host = peers.resolve(role, own_role=own_role, own_ip=own_ip, be_host=be_host, allow_scan=True)
            if host:
                log(f"peer {role}: {host} (verificato)")
                break
            time.sleep(10)  # the other PC may simply not be up yet


def start_showcase(role: str, root: Path, hosts: dict[str, str]) -> list["subprocess.Popen[bytes]"]:
    """Start the extra servers of ``role`` and schedule the browser tabs. Returns processes to clean up."""
    venv_python = root / ".venv" / "Scripts" / "python.exe"
    exe = str(venv_python) if venv_python.exists() else sys.executable
    procs: list[subprocess.Popen[bytes]] = []
    own_ip = peers._own_ip()
    be_host = peers._be_host_from_env()

    # the voice server finds the CHAT PC lazily through this file (see voicebot.peers_file); no stale IP at start-up
    os.environ.setdefault("AI4R_PEERS_FILE", str(peers.PEERS_FILE))

    if _port_busy(SHOWCASE_PORT):
        if not _showcase_is_current():
            log(f"ATTENZIONE: sulla porta {SHOWCASE_PORT} gira un vecchio server (avviato a mano o da una versione "
                f"precedente). Chiudilo: Get-NetTCPConnection -LocalPort {SHOWCASE_PORT} -State Listen | % "
                "{ Stop-Process -Id $_.OwningProcess -Force }")
    else:
        procs.append(subprocess.Popen([exe, str(root / "showcase" / "serve.py"), "--port", str(SHOWCASE_PORT)],
                                      cwd=str(root)))
    if role == "chat":
        if _port_busy(FRONTEND_PORT):
            log(f"porta {FRONTEND_PORT} gia' occupata: se non e' il sito di frontend/ aggiornato, chiudi il processo vecchio")
        else:  # the chat colleague's own page, automatic
            procs.append(subprocess.Popen([exe, "-m", "http.server", str(FRONTEND_PORT), "--directory", "frontend"],
                                          cwd=str(root)))

    log("pagine di questa macchina (indirizzi facili da ricordare):")
    mine = OPEN.get(role, [])
    for key in mine:
        log(f"   {key:<9} {NAMES[key]}")
    log("elenco completo dei siti: docs/SITI.md")
    threading.Thread(target=_discover_in_background, args=(role, own_ip, be_host), daemon=True).start()
    if os.environ.get("AI4R_NO_BROWSER") != "1":
        threading.Thread(target=_wait_and_open, args=(mine,), daemon=True).start()
    return procs
