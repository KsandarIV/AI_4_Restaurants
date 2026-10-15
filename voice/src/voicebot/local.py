"""``python -m voicebot local`` - a complete local test with one command.

Starts a stub BE (same contract as the real one: registration, booking with confirmation,
cancel/modify, menu, info) and the voice server pointed at it, then opens the site in the
browser. Nothing else is needed: no BE machine, no Ollama, no database - and nothing you
do here touches the real restaurant data.

Real STT/TTS models are used (the first start downloads Whisper); ``--fake`` skips them to
test only the page and the flow.
"""

from __future__ import annotations

import socket
import threading
import time
import webbrowser

import uvicorn

from .config import Settings, get_settings
from .devtools.stub_be import make_stub
from .logging_json import setup_logging
from .pipeline.server import create_app


def pick_port(preferred: int, *, host: str = "127.0.0.1", attempts: int = 20) -> int:
    """First free TCP port starting from ``preferred`` (so a leftover voice bot does not block you)."""
    for port in range(preferred, preferred + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            if sock.connect_ex((host, port)) != 0:  # nobody is listening: free
                return port
    raise RuntimeError(f"no free port in {preferred}-{preferred + attempts - 1}")


def local_settings(be_url: str, port: int, fake: bool) -> Settings:
    """The machine's settings, pointed at the stub BE."""
    update: dict[str, object] = {
        "backend_base_url": be_url, "voice_port": port, "voice_host": "127.0.0.1", "mode": "local",
        "preload_models": True,
    }
    if fake:
        update.update({"stt_backend": "fake", "tts_backend": "fake"})
    return get_settings().model_copy(update=update)


def run_local(fake: bool = False, port: int = 0, open_browser: bool = True) -> int:
    """Run stub BE + voice server in this process until Ctrl+C."""
    be_port = pick_port(8001)
    voice_port = port or pick_port(8003)
    stub, be_url, _ = make_stub(port=be_port)
    settings = local_settings(be_url, voice_port, fake)
    setup_logging(settings.log_level)
    url = f"http://localhost:{voice_port}/"
    print("=" * 66)
    print(" VOICE - LOCAL TEST")
    print(f"   site (open this)  : {url}")
    print(f"   stub BE           : {be_url}   (no LLM, nothing is saved anywhere)")
    print(f"   models            : {'FAKE (no speech)' if fake else 'real Whisper + Piper (first start downloads Whisper)'}")
    print("   try: wait for the greeting, say 'Mario Rossi, 333 1234567', 'sì',")
    print("        then 'vorrei prenotare un tavolo per due persone domani alle 21', 'sì'.")
    print("   stop with Ctrl+C")
    print("=" * 66, flush=True)
    app = create_app(settings)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=voice_port, ws="auto",
                                           log_config=None, timeout_graceful_shutdown=5))

    def _open() -> None:
        while not server.started:
            time.sleep(0.2)
        if open_browser:
            webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    finally:
        stub.shutdown()
    return 0
