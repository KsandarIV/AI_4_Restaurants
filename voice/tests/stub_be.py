"""Local stub of the BE for offline voice tests and local demos (stdlib only).

Mimics the real BE contract (backend/api/routes.py): health, customer registration
(E.164 validation, 422 on bad data), chat + SSE stream with the registration rule and the
yes/no booking confirmation, availability, reservations CRUD, menu, info.
Tests:   `make_stub()` returns (server, base_url, state); stop with `server.shutdown()`.
Manual:  `python tests/stub_be.py [port]`  (default 8000).

KEEP IN SYNC with backend/api/routes.py (docs/AGENTS.md section 2.6).
"""

from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse, parse_qs

MENU = [
    {"name": "Bruschetta", "category": "Antipasti", "price": 6.5},
    {"name": "Pizza Margherita", "category": "Primi", "price": 9.0},
    {"name": "Tiramisu", "category": "Dessert", "price": 5.0},
]
INFO = {"address": "Via Roma 1", "phone": "081 000000", "opening_hours": "12-15 / 19-23:30"}


_PHONE = re.compile(r"^\+[1-9]\d{7,14}$")
_BOOK = re.compile(r"prenot|tavolo|book|reserv", re.I)
_YES = re.compile(r"^\W*(?:s[ìi]|yes|ok|certo|confermo)\b", re.I)


class StubState:
    """Shared state: customers, reservations and every request received (for assertions)."""

    def __init__(self) -> None:
        self.reservations: dict[str, dict[str, Any]] = {}
        self.customers: dict[str, dict[str, str]] = {}
        self.pending: dict[str, str] = {}  # session_id -> booking waiting for "yes"
        self.counter = 0
        self.last_chat_payload: dict[str, Any] = {}
        self.chat_payloads: list[dict[str, Any]] = []
        self.fail_chat_status = 0  # >0: /api/chat and /api/chat/stream answer this status
        self.chat_delay_s = 0.0  # simulated LLM latency before answering


def _converse(state: StubState, body: dict[str, Any], message: str) -> str:
    """The stub "LLM": registration rule + confirmation protocol like the real agent."""
    session = str(body.get("session_id", "stub_sess"))
    customer = str(body.get("customer_id") or "anon_stub")
    low = message.lower()
    if session in state.pending and _YES.match(message):
        state.counter += 1
        code = f"RES-STUB{state.counter:02d}"
        state.reservations[code] = {"success": True, "booking_code": code,
                                    "customer_id": customer, "details": state.pending.pop(session)}
        return f"Prenotazione confermata. Il codice è {code}."
    if _BOOK.search(message):
        if customer.startswith("anon_"):
            return "Per prenotare serve prima la registrazione di nome e telefono."
        state.pending[session] = message
        return "Tavolo per due persone domani alle venti. Confermi?"
    if "menu" in low:
        return "Abbiamo bruschetta, pizza margherita e tiramisù."
    if "orari" in low or "aprite" in low:
        return "Siamo aperti a pranzo dalle dodici e a cena dalle diciannove."
    return f"[Stub BE] Ho ricevuto: {message}"


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
            self._json(200, {"status": "online", "restaurant": "Stub", "llm_provider": "stub",
                             "llm_model": "stub-model", "llm_reachable": True,
                             "llm_model_available": True, "database": "SQLite (connected)"})
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
        if path in ("/api/customers", "/customers"):
            body = self._body()
            name = str(body.get("name", "")).strip()
            phone = str(body.get("phone", ""))
            if not name or not _PHONE.match(phone) or body.get("consent") is not True:
                self._json(422, {"detail": "invalid customer data"})
                return
            customer_id = f"cust_{len(st.customers) + 1:012x}"
            st.customers[customer_id] = {"name": name, "phone": phone}
            self._json(200, {"customer_id": customer_id})
        elif path in ("/api/chat", "/chat"):
            body = self._body()
            st.last_chat_payload = body
            st.chat_payloads.append(body)
            if st.chat_delay_s:
                time.sleep(st.chat_delay_s)
            if st.fail_chat_status:
                self._json(st.fail_chat_status, {"detail": "stub failure"})
                return
            msg = str(body.get("message", ""))
            sess = str(body.get("session_id", "stub_sess"))
            self._json(200, {"reply": _converse(st, body, msg), "session_id": sess,
                             "customer_id": body.get("customer_id") or f"anon_{sess}",
                             "client_type": body.get("client_type", "chat"),
                             "timestamp": "2026-01-01T00:00:00Z"})
        elif path in ("/api/chat/stream", "/chat/stream"):
            body = self._body()
            st.last_chat_payload = body
            st.chat_payloads.append(body)
            if st.chat_delay_s:
                time.sleep(st.chat_delay_s)
            if st.fail_chat_status:
                self._json(st.fail_chat_status, {"detail": "stub failure"})
                return
            msgs = body.get("messages") or []
            text = next((str(m.get("content", "")) for m in reversed(msgs)
                         if m.get("role") == "user"), str(body.get("message", "Buongiorno")))
            reply = _converse(st, body, text)
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
