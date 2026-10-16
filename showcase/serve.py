"""The complete site, served locally so the microphone works (http://completo.localhost:8090/).

It is the voice site (voice/src/voicebot/pipeline/site: restaurant, orb button with its animations, chat window,
"My reservations") served from THIS machine, plus the restaurateur area, and wired to the other services:

    browser (secure context: *.localhost) --> this server  : page, staff.html, static assets
                                          +-> VOICE PC :8003: WebSocket /ws/voice, /site/*   (chat window goes on
                                                              from there to the CHAT PC :8002)
                                          +-> BE PC    :8000: staff area (X-API-Key), Swagger

Why served locally: browsers expose the microphone only to secure contexts; http://localhost and any *.localhost is
one, http://<LAN-IP> is not. So every PC serves the same page on its own loopback and talks to the others over the LAN.

The voice PC is resolved at EVERY page load (showcase.peers: verified, cached, rediscovered), never frozen at start-up:
starting this server before the voice PC, or after its address changed, needs no restart.

    python showcase/serve.py [--voice auto|http://IP:8003] [--be http://IP:8000] [--port 8090]

Stdlib only. Files are read per request: a `git pull` is enough to update the page.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from showcase import peers  # noqa: E402

VERSION = 2
SITE_DIR = ROOT / "voice" / "src" / "voicebot" / "pipeline" / "site"
FRONTEND_DIR = ROOT / "frontend"
_APP_TAG = '<script src="/site-assets/app.js"></script>'
_STATIC_PREFIXES = ("/css/", "/js/")
_TTL_S = 10.0  # how long a resolved voice address is trusted before it is verified again


class VoiceResolver:
    """Resolves the voice PC lazily and verifies it again after ``_TTL_S``."""

    def __init__(self, fixed: str, own_ip: str, be_host: str) -> None:
        self._fixed, self._own_ip, self._be_host = fixed.rstrip("/"), own_ip, be_host
        self._value, self._at = "", 0.0

    def base(self) -> str:
        """``http://<host>:8003`` or '' when the voice PC cannot be found right now."""
        if self._fixed:
            return self._fixed
        if time.monotonic() - self._at > _TTL_S:
            host = peers.resolve("voice", own_ip=self._own_ip, be_host=self._be_host, allow_scan=True)
            self._value, self._at = (f"http://{host}:8003" if host else ""), time.monotonic()
        return self._value


def _be_base(be: str) -> str:
    return (be or f"http://{peers._be_host_from_env() or '127.0.0.1'}:8000").rstrip("/")


def render_index(voice_base: str, be_base: str, gateway: bool = False) -> bytes:
    """index.html of the voice site wired to the voice PC, with the operator tools in the footer."""
    html = (SITE_DIR / "index.html").read_text(encoding="utf-8")
    inject = f'<script>window.VOICE_BASE = {json.dumps(voice_base)};</script>\n  {_APP_TAG}'
    html = html.replace(_APP_TAG, inject, 1)
    # behind the BE gateway the voice test page would miss its WebSocket route: link the diagnostics instead
    page = "diag" if gateway else "test-voice"
    html = html.replace('href="/prova-vocale"', f'href="{voice_base or "#"}/{page}"')
    links = [("/staff.html", "Area ristoratore"), (f"{be_base}/docs", "Swagger del BE"),
             (f"{be_base}/api/health", "Salute del BE")]
    if voice_base:
        links.append((f"{voice_base}/diag", "Diagnosi voce"))
    tools = ('<p class="tools" style="margin-top:10px;font-family:system-ui,sans-serif;font-size:.85rem">'
             + " · ".join(f'<a style="color:inherit" href="{href}">{label}</a>' for href, label in links) + "</p>")
    html = html.replace("</footer>", tools + "\n  </footer>", 1)
    if not voice_base:
        warn = ('<div style="background:#fff3cd;border-bottom:1px solid #e0a800;padding:8px 14px;font-family:system-ui,'
                'sans-serif;font-size:.85rem;text-align:center">Il PC della voce non risponde: avvia '
                '<code>python entrypoint\\avvia.py</code> su quella macchina, oppure '
                '<code>python -m showcase.peers set voice &lt;IP&gt;</code>. La pagina si riconnette da sola al ricaricamento.</div>')
        html = html.replace("<body>", "<body>\n" + warn, 1)
    return html.encode("utf-8")


def render_config_js(be_base: str) -> bytes:
    """frontend/js/config.js with the BE address of THIS LAN instead of the one committed in the file."""
    text = (FRONTEND_DIR / "js" / "config.js").read_text(encoding="utf-8")
    text = re.sub(r'baseUrl:\s*"http://[^"]+:8000"', f'baseUrl: "{be_base}"', text, count=1)
    return text.encode("utf-8")


def _mime(name: str) -> str:
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return ctype + ("; charset=utf-8" if ctype.startswith("text") or ctype.endswith("javascript") else "")


def make_handler(voice: VoiceResolver, be: str = "") -> type[BaseHTTPRequestHandler]:
    """Request handler bound to the resolvers."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:  # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _file(self, base: Path, rel: str) -> None:
            target = (base / rel).resolve()
            if base.resolve() in target.parents and target.is_file():
                self._send(200, target.read_bytes(), _mime(target.name))
            else:
                self._send(404, b"not found", "text/plain")

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self._send(200, render_index(voice.base(), _be_base(be)), "text/html; charset=utf-8")
            elif path == "/health":
                body = json.dumps({"status": "ok", "version": VERSION, "voice": voice.base()}).encode()
                self._send(200, body, "application/json")
            elif path.startswith("/site-assets/"):
                self._file(SITE_DIR, path[len("/site-assets/"):])
            elif path == "/staff.html":
                self._file(FRONTEND_DIR, "staff.html")
            elif path == "/js/config.js":
                self._send(200, render_config_js(_be_base(be)), "application/javascript; charset=utf-8")
            elif path.startswith(_STATIC_PREFIXES):  # frontend/css and frontend/js only: read-only, never modified
                folder, _, rel = path.lstrip("/").partition("/")
                self._file(FRONTEND_DIR / folder, rel)  # the base is the folder: ".." cannot reach its siblings
            else:
                self._send(404, b"not found", "text/plain")

    return Handler


def main(argv: list[str] | None = None) -> int:
    """Run the server until Ctrl+C."""
    parser = argparse.ArgumentParser(description="Complete site (voice + chat + staff) served locally.")
    parser.add_argument("--voice", default="auto", help="voice server base URL, or 'auto' (default): discovered")
    parser.add_argument("--be", default="", help="BE base URL (default: BACKEND_BASE_URL of .env)")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args(argv)
    if not SITE_DIR.is_dir():
        print(f"[showcase] voice site not found at {SITE_DIR}", file=sys.stderr)
        return 1
    resolver = VoiceResolver("" if args.voice == "auto" else args.voice, peers._own_ip(), peers._be_host_from_env())
    server = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(resolver, args.be))
    print(f"[showcase] complete site: http://completo.localhost:{args.port}/  (voice: {args.voice}, BE: {_be_base(args.be)})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
