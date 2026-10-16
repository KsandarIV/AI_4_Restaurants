"""Starts the demo sites of a machine and opens them in the browser (called by lan/machine_setup.py).

Easy addresses (``*.localhost`` always means "this PC" and counts as a secure page: the microphone works):

    solo-be.localhost:8080         the site WITHOUT working chat/voice (they appear bottom-right)       [BE]
    completo.localhost:8090        the COMPLETE site: chat + voice working across the three PCs        [all]
    chat.localhost:8080            the chat colleague's own site (frontend/), chat working            [CHAT]
    voce.localhost:8003/test-voice the voice test page: orb + STATO / TECNICA tabs                    [VOICE]

Set AI4R_NO_BROWSER=1 to start the servers without opening the browser.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

SHOWCASE_PORT = 8090
FRONTEND_PORT = 8080
VOICE_PORT = 8003
CHAT_API_PORT = 8002

NAMES = {
    "solo-be": f"http://solo-be.localhost:{FRONTEND_PORT}/",
    "completo": f"http://completo.localhost:{SHOWCASE_PORT}/",
    "chat": f"http://chat.localhost:{FRONTEND_PORT}/",
    "voce": f"http://voce.localhost:{VOICE_PORT}/test-voice",
}
# What answers locally when the page is ready (probe), per page.
PROBES = {
    "solo-be": f"http://127.0.0.1:{FRONTEND_PORT}/",
    "completo": f"http://127.0.0.1:{SHOWCASE_PORT}/",
    "chat": f"http://127.0.0.1:{FRONTEND_PORT}/",
    "voce": f"http://127.0.0.1:{VOICE_PORT}/health",
}
# Pages opened automatically per role.
OPEN = {"be": ["solo-be", "completo"], "chat": ["chat"], "voice": ["voce"]}


def log(msg: str) -> None:
    """Prefixed console line."""
    print(f"[showcase] {msg}", flush=True)


def _port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex(("127.0.0.1", port)) == 0


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


def start_showcase(role: str, root: Path, hosts: dict[str, str]) -> list["subprocess.Popen[bytes]"]:
    """Start the extra servers of ``role`` and schedule the browser tabs. Returns processes to clean up."""
    venv_python = root / ".venv" / "Scripts" / "python.exe"
    exe = str(venv_python) if venv_python.exists() else sys.executable
    procs: list[subprocess.Popen[bytes]] = []

    voice_host = "127.0.0.1" if role == "voice" else hosts.get("voice", "127.0.0.1")
    chat_host = "127.0.0.1" if role == "chat" else hosts.get("chat", "127.0.0.1")
    if role == "voice":  # the complete site's chat window goes through the voice server to the CHAT PC
        os.environ.setdefault("CHAT_SERVICE_URL", f"http://{chat_host}:{CHAT_API_PORT}")

    if not _port_busy(SHOWCASE_PORT):
        procs.append(subprocess.Popen(
            [exe, str(root / "showcase" / "serve.py"), "--voice", f"http://{voice_host}:{VOICE_PORT}",
             "--port", str(SHOWCASE_PORT)], cwd=str(root)))
    if role == "chat" and not _port_busy(FRONTEND_PORT):  # the chat colleague's own page, automatic
        procs.append(subprocess.Popen(
            [exe, "-m", "http.server", str(FRONTEND_PORT), "--directory", "frontend"], cwd=str(root)))

    log("pagine di questa macchina (indirizzi facili da ricordare):")
    mine = OPEN.get(role, [])
    for key in mine + ([] if "completo" in mine else ["completo"]):
        log(f"   {key:<9} {NAMES[key]}")
    if os.environ.get("AI4R_NO_BROWSER") != "1":
        threading.Thread(target=_wait_and_open, args=(mine,), daemon=True).start()
    return procs
