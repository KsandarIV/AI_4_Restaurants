"""The complete site, served locally so the microphone works (http://completo.localhost:8090/).

It is the voice site (voice/src/voicebot/pipeline/site: restaurant, orb button with its animations, the
chat window, "My reservations") served from THIS machine and pointed at the PC that runs the voice server:

    voice (ws + /site/*) -> http://<VOICE-PC>:8003        chat window -> voice server -> CHAT PC (:8002)

Why locally: browsers give the microphone only to "secure" pages. http://localhost (and any *.localhost) counts
as secure, http://<some-LAN-IP> does not. So every PC serves the same page on its own localhost and talks to the
voice PC over the network, as the brief wants.

    python showcase/serve.py --voice http://192.168.1.12:8003 [--port 8090]

Stdlib only. Files are read at every request: a `git pull` is enough to update the page.
"""

from __future__ import annotations

import argparse
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = ROOT / "voice" / "src" / "voicebot" / "pipeline" / "site"
_APP_TAG = '<script src="/site-assets/app.js"></script>'


def render_index(voice_base: str) -> bytes:
    """index.html of the voice site with the voice PC's address injected."""
    html = (SITE_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace(_APP_TAG, f'<script>window.VOICE_BASE = "{voice_base}";</script>\n  {_APP_TAG}', 1)
    # the footer link to the test page must point at the voice PC, not at this server
    return html.replace('href="/prova-vocale"', f'href="{voice_base}/test-voice"').encode("utf-8")


def make_handler(voice_base: str) -> type[BaseHTTPRequestHandler]:
    """Request handler bound to the voice PC's address."""

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

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self._send(200, render_index(voice_base), "text/html; charset=utf-8")
            elif path == "/health":
                self._send(200, b'{"status":"ok"}', "application/json")
            elif path.startswith("/site-assets/"):
                target = (SITE_DIR / path[len("/site-assets/"):]).resolve()
                if SITE_DIR in target.parents and target.is_file():
                    ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                    if ctype.startswith("text") or ctype.endswith("javascript"):
                        ctype += "; charset=utf-8"
                    self._send(200, target.read_bytes(), ctype)
                else:
                    self._send(404, b"not found", "text/plain")
            else:
                self._send(404, b"not found", "text/plain")

    return Handler


def main(argv: list[str] | None = None) -> int:
    """Run the server until Ctrl+C."""
    parser = argparse.ArgumentParser(description="Complete site (voice + chat) served locally.")
    parser.add_argument("--voice", required=True, help="voice server base URL, e.g. http://192.168.1.12:8003")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args(argv)
    voice_base = args.voice.rstrip("/")
    if not SITE_DIR.is_dir():
        print(f"[showcase] voice site not found at {SITE_DIR}", file=sys.stderr)
        return 1
    server = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(voice_base))
    print(f"[showcase] complete site: http://completo.localhost:{args.port}/  (voice PC: {voice_base})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
