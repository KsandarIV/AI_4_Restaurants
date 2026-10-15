"""Stub BE locale per i test Voice offline (solo stdlib, nessuna dipendenza).

Imita il contratto del BE vero (backend/api/routes.py) COMPRESE le parti che
il finto BE di chat/ NON copre: stream SSE, availability e CRUD prenotazioni.
Uso nei test: `make_stub()` ritorna (server, base_url); chiudere con
`server.shutdown()`. Uso manuale: `python stub_be.py` (porta 8000).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse, parse_qs

MENU = [
    {"name": "Bruschetta", "category": "Antipasti", "price": 6.5},
    {"name": "Pizza Margherita", "category": "Primi", "price": 9.0},
    {"name": "Tiramisu", "category": "Dessert", "price": 5.0},
]
INFO = {"address": "Via Roma 1", "phone": "081 000000", "opening_hours": "12-15 / 19-23:30"}


class StubState:
    """Stato condiviso: prenotazioni + ultimo payload ricevuto (per test PII)."""

    def __init__(self) -> None:
        self.reservations: dict[str, dict[str, Any]] = {}
        self.counter = 0
        self.last_chat_payload: dict[str, Any] = {}


def _reply_for(message: str) -> str:
    if "prenot" in message.lower():
        return "Prenotazione confermata! Codice: RES-STUB01."
    return f"[Stub BE] Ho ricevuto: «{message}»."


class Handler(BaseHTTPRequestHandler):
    state: StubState = StubState()  # sostituito per-istanza da make_stub

    def log_message(self, *args: object) -> None:
        pass  # test silenziosi

    # -- helpers --
    def _json(self, code: int, body: Any) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict[str, Any]:
        try:
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
            return json.loads(raw or b"{}")
        except ValueError:
            return {}

    def _path(self) -> tuple[str, dict[str, list[str]]]:
        parsed = urlparse(self.path)
        return parsed.path, parse_qs(parsed.query)

    # -- GET --
    def do_GET(self) -> None:
        path, qs = self._path()
        st = self.state
        if path in ("/health", "/api/health"):
            self._json(200, {"status": "online", "restaurant": "Stub", "llm_provider": "stub"})
        elif path in ("/api/menu", "/menu"):
            self._json(200, MENU)
        elif path in ("/api/info", "/info"):
            self._json(200, INFO)
        elif path in ("/api/availability", "/availability"):
            party = int((qs.get("party_size") or qs.get("guests") or ["2"])[0])
            self._json(200, {"available": True, "tables_count": 3,
                             "date": (qs.get("date") or [""])[0],
                             "time": (qs.get("time") or [""])[0], "party_size": party})
        elif path.startswith(("/api/reservations/", "/reservations/")):
            code = path.rsplit("/", 1)[-1]
            res = st.reservations.get(code)
            if res is None:
                self._json(404, {"detail": f"Prenotazione {code} non trovata."})
            else:
                self._json(200, res)
        else:
            self._json(404, {"detail": "Not Found"})

    # -- POST --
    def do_POST(self) -> None:
        path, _ = self._path()
        st = self.state
        if path in ("/api/chat", "/chat"):
            body = self._body()
            st.last_chat_payload = body
            msg = str(body.get("message", ""))
            sess = str(body.get("session_id", "stub_sess"))
            self._json(200, {"reply": _reply_for(msg), "session_id": sess,
                             "customer_id": body.get("customer_id") or f"anon_{sess}",
                             "client_type": body.get("client_type", "chat"),
                             "timestamp": "2026-01-01T00:00:00Z"})
        elif path in ("/api/chat/stream", "/chat/stream"):
            body = self._body()
            st.last_chat_payload = body
            msgs = body.get("messages") or []
            text = next((str(m.get("content", "")) for m in reversed(msgs)
                         if m.get("role") == "user"), str(body.get("message", "Buongiorno")))
            reply = _reply_for(text)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.end_headers()
            words = reply.split(" ")
            for i, word in enumerate(words):
                token = word + (" " if i < len(words) - 1 else "")
                self.wfile.write(f"data: {json.dumps({'token': token})}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
        elif path in ("/api/reservations", "/reservations"):
            body = self._body()
            guests = body.get("guests") or body.get("party_size") or 2
            st.counter += 1
            code = f"RES-STUB{st.counter:02d}"
            res = {"success": True, "booking_code": code, "date": body.get("date"),
                   "time": body.get("time"), "guests": guests,
                   "customer_id": body.get("customer_id") or body.get("name") or "anon_client"}
            st.reservations[code] = res
            self._json(200, res)
        else:
            self._json(404, {"detail": "Not Found"})

    def _modify(self) -> None:
        path, _ = self._path()
        st = self.state
        code = path.rsplit("/", 1)[-1]
        res = st.reservations.get(code)
        if res is None:
            self._json(404, {"detail": f"Prenotazione {code} non trovata."})
            return
        body = self._body()
        if body.get("new_date"):
            res["date"] = body["new_date"]
        if body.get("new_time"):
            res["time"] = body["new_time"]
        if body.get("new_guests") or body.get("party_size"):
            res["guests"] = body.get("new_guests") or body.get("party_size")
        res["success"] = True
        self._json(200, res)

    def do_PATCH(self) -> None:
        self._modify()

    def do_PUT(self) -> None:
        self._modify()

    def do_DELETE(self) -> None:
        path, _ = self._path()
        st = self.state
        code = path.rsplit("/", 1)[-1]
        if code not in st.reservations:
            self._json(404, {"detail": f"Prenotazione {code} non trovata."})
            return
        del st.reservations[code]
        self._json(200, {"success": True, "booking_code": code, "cancelled": True})


def make_stub() -> tuple[ThreadingHTTPServer, str, StubState]:
    """Avvia lo stub su porta effimera in thread daemon. Ritorna (server, base_url, state)."""
    state = StubState()
    handler = type("StubHandler", (Handler,), {"state": state})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{port}", state


if __name__ == "__main__":
    import sys

    try:
        port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    except ValueError:
        raise SystemExit("uso: python tests/stub_be.py [porta]  (default 8000)")
    state = StubState()
    Handler.state = state
    print(f"Stub BE Voice su http://0.0.0.0:{port}  (Ctrl+C per fermare)")
    try:
        ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
    except OSError as exc:
        raise SystemExit(f"porta {port} occupata ({exc}): libera la {port} o lancia con un'altra "
                         f"(es. python tests/stub_be.py 8001)")
