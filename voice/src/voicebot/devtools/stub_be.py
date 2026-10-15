"""Local stub of the BE for offline voice tests and local demos (stdlib only).

Mimics the real BE contract (``backend/api/routes.py``): health, customer registration (E.164
validation, 422 on bad data), chat + SSE stream with the registration rule and the yes/no booking
confirmation, cancel/modify by code, reservation lookup restricted to the owner, menu, info.

Used by ``python -m voicebot local`` and by the tests (``tests/stub_be.py`` re-exports it).
Standalone: ``python voice/tests/stub_be.py [port]`` (default 8000).

KEEP IN SYNC with backend/api/routes.py (docs/AGENTS.md section 2.6).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

MENU = [
    {"category": "Antipasti", "name": "Bruschetta al pomodoro", "description": "Pane casereccio, San Marzano, basilico",
     "price": 6.5, "allergens": "glutine", "is_vegetarian": True, "is_vegan": True, "is_gluten_free": False},
    {"category": "Antipasti", "name": "Mozzarella di bufala", "description": "Con pomodorini e olio nuovo",
     "price": 9.0, "allergens": "latte", "is_vegetarian": True, "is_vegan": False, "is_gluten_free": True},
    {"category": "Primi", "name": "Spaghetti alle vongole", "description": "Spaghetti di Gragnano e vongole veraci",
     "price": 15.0, "allergens": "glutine, molluschi", "is_vegetarian": False, "is_vegan": False, "is_gluten_free": False},
    {"category": "Secondi", "name": "Frittura di paranza", "description": "Pescato del giorno",
     "price": 17.0, "allergens": "pesce, glutine", "is_vegetarian": False, "is_vegan": False, "is_gluten_free": False},
    {"category": "Dessert", "name": "Babà al rum", "description": "Il classico napoletano",
     "price": 6.0, "allergens": "glutine, uova, latte", "is_vegetarian": True, "is_vegan": False, "is_gluten_free": False},
    {"category": "Dessert", "name": "Sorbetto al limone", "description": "Limoni di Sorrento",
     "price": 5.0, "allergens": "", "is_vegetarian": True, "is_vegan": True, "is_gluten_free": True},
]
INFO = {
    "name": "Trattoria Bella Napoli (stub)",
    "address": "Via Toledo 142, 80134 Napoli (NA)",
    "phone": "+39 081 555 1234",
    "email": "prenotazioni@trattoriabellanapoli.it",
    "opening_hours": "Dal martedì alla domenica. Pranzo 12:00-15:00, cena 19:30-23:30. Lunedì chiuso.",
    "parking": "Convenzione con il Garage Toledo, a 50 metri dal locale.",
    "services": "Terrazza e giardino, WiFi gratuito, accesso per disabili, seggioloni. Animali ammessi.",
    "payment_methods": "Contanti, carte, Bancomat, Apple Pay e Satispay.",
}

_PHONE = re.compile(r"^\+[1-9]\d{7,14}$")
_BOOK = re.compile(r"prenot|tavolo|book|reserv", re.I)
_YES = re.compile(r"^\W*(?:s[ìi]|yes|ok|certo|confermo)\b", re.I)
_CODE = re.compile(r"RES-[A-Z0-9]{4,10}", re.I)
_GUESTS = re.compile(r"(\d{1,2})\s*(?:pers|ospit|coperti|people)", re.I)
_TIME = re.compile(r"alle\s+(\d{1,2})(?:[:.](\d{2}))?", re.I)
_WORD_NUMBERS = {"una": 1, "uno": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7,
                 "otto": 8, "nove": 9, "dieci": 10}
_WORD_HOURS = {"diciannove": 19, "venti": 20, "ventuno": 21, "ventidue": 22, "dodici": 12, "tredici": 13}


class StubState:
    """Shared state: customers, reservations and every request received (for assertions)."""

    def __init__(self) -> None:
        self.reservations: dict[str, dict[str, Any]] = {}
        self.customers: dict[str, dict[str, str]] = {}
        self.pending: dict[str, dict[str, Any]] = {}  # session_id -> booking waiting for "yes"
        self.counter = 0
        self.last_chat_payload: dict[str, Any] = {}
        self.chat_payloads: list[dict[str, Any]] = []
        self.fail_chat_status = 0  # >0: /api/chat and /api/chat/stream answer this status
        self.chat_delay_s = 0.0  # simulated LLM latency before answering


def _parse_booking(message: str) -> dict[str, Any]:
    """Very small 'NLU': party size, hour and day from the sentence, with sensible defaults."""
    low = message.lower()
    guests = 2
    if m := _GUESTS.search(low):
        guests = int(m.group(1))
    else:
        for word, value in _WORD_NUMBERS.items():
            if re.search(rf"per\s+{word}\b", low):
                guests = value
    hour, minute = 20, 30
    if m := _TIME.search(low):
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        if not m.group(2) and re.search(r"alle\s+\d{1,2}\s+e\s+(?:30|trenta|mezza)", low):  # STT: "alle 20 e 30"
            minute = 30
    else:
        for word, value in _WORD_HOURS.items():
            if re.search(rf"alle\s+{word}\b", low):
                hour, minute = value, 30 if re.search(r"e\s+(?:trenta|mezza)", low) else 0
    day = dt.date.today() + dt.timedelta(days=1 if "domani" in low or "tomorrow" in low else 2)
    return {"date": day.isoformat(), "time": f"{hour:02d}:{minute:02d}", "guests": guests}


def _public(res: dict[str, Any]) -> dict[str, Any]:
    """The reservation as ``ReservationResponse`` exposes it."""
    return {"success": True, "booking_code": res["booking_code"], "date": res["date"], "time": res["time"],
            "shift": "dinner" if res["time"] >= "17:00" else "lunch", "guests_count": res["guests_count"],
            "table_number": res["table_number"], "table_location": res["table_location"],
            "status": res["status"], "special_requests": None}


def _owned(state: StubState, code: str, customer: str | None) -> dict[str, Any] | None:
    res = state.reservations.get(code.upper())
    return res if res and customer and res["customer_id"] == customer else None


def _converse(state: StubState, body: dict[str, Any], message: str) -> str:
    """The stub "LLM": registration rule + confirmation protocol like the real agent."""
    session = str(body.get("session_id", "stub_sess"))
    customer = str(body.get("customer_id") or "anon_stub")
    low = message.lower()
    registered = not customer.startswith("anon_")
    code_match = _CODE.search(message)

    if session in state.pending and _YES.match(message):
        state.counter += 1
        code = f"RES-STUB{state.counter:02d}"
        booking = state.pending.pop(session)
        state.reservations[code] = {
            "booking_code": code, "customer_id": customer, "status": "CONFIRMED",
            "table_number": 10 + state.counter, "table_location": "terrazza",
            "date": booking["date"], "time": booking["time"], "guests_count": booking["guests"],
        }
        return f"Prenotazione confermata. Il codice è {code}."
    if code_match and re.search(r"cancell|annull|cancel", low):
        res = _owned(state, code_match.group(), customer)
        if res is None:
            return "Non trovo nessuna prenotazione con questo codice."
        res["status"] = "CANCELLED"
        return f"La prenotazione {res['booking_code']} è stata cancellata."
    if code_match and re.search(r"modific|cambia|sposta|change", low):
        res = _owned(state, code_match.group(), customer)
        if res is None:
            return "Non trovo nessuna prenotazione con questo codice."
        new = _parse_booking(message)
        if _TIME.search(low):
            res["time"] = new["time"]
        if _GUESTS.search(low):
            res["guests_count"] = new["guests"]
        return f"Ho aggiornato la prenotazione {res['booking_code']}."
    if _BOOK.search(message):
        if not registered:
            return "Per prenotare serve prima la registrazione di nome e telefono."
        booking = _parse_booking(message)
        state.pending[session] = booking
        return f"Tavolo per {booking['guests']} persone il {booking['date']} alle {booking['time']}. Confermi?"
    if "menu" in low or "dolci" in low or "dessert" in low:
        return "Abbiamo bruschetta, mozzarella di bufala, spaghetti alle vongole, babà e sorbetto al limone."
    if "orari" in low or "aprite" in low:
        return "Siamo aperti a pranzo dalle dodici e a cena dalle diciannove e trenta."
    return f"[Stub BE] Ho ricevuto: {message}"


class Handler(BaseHTTPRequestHandler):
    state: StubState = StubState()  # replaced per instance by make_stub

    def log_message(self, *args: object) -> None:
        pass  # quiet

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
            return json.loads(raw or b"{}")  # type: ignore[no-any-return]
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
            self._json(200, {"available": True, "tables_count": 3, "date": (qs.get("date") or [""])[0],
                             "time": (qs.get("time") or [""])[0], "party_size": party})
        elif path.startswith(("/api/reservations/", "/reservations/")):
            code = path.rsplit("/", 1)[-1]
            res = _owned(st, code, (qs.get("customer_id") or [None])[0])  # type: ignore[list-item]
            if res is None:  # same answer for "missing" and "someone else's": codes are not guessable
                self._json(404, {"detail": f"Prenotazione {code} non trovata."})
            else:
                self._json(200, _public(res))
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
            st.counter += 1
            code = f"RES-STUB{st.counter:02d}"
            res = {"booking_code": code, "customer_id": body.get("customer_id") or "anon_client",
                   "status": "CONFIRMED", "table_number": 10 + st.counter, "table_location": "interno",
                   "date": body.get("date"), "time": body.get("time"),
                   "guests_count": body.get("guests") or body.get("party_size") or 2}
            st.reservations[code] = res
            self._json(200, _public(res))
        else:
            self._json(404, {"detail": "Not Found"})

    def _modify(self) -> None:
        path, _ = self._path()
        body = self._body()
        res = _owned(self.state, path.rsplit("/", 1)[-1], body.get("customer_id"))
        if res is None:
            self._json(404, {"detail": "Prenotazione non trovata."})
            return
        res["date"] = body.get("new_date") or res["date"]
        res["time"] = body.get("new_time") or res["time"]
        res["guests_count"] = body.get("new_guests") or body.get("party_size") or res["guests_count"]
        self._json(200, _public(res))

    def do_PATCH(self) -> None:
        self._modify()

    def do_PUT(self) -> None:
        self._modify()

    def do_DELETE(self) -> None:
        path, qs = self._path()
        res = _owned(self.state, path.rsplit("/", 1)[-1], (qs.get("customer_id") or [None])[0])  # type: ignore[list-item]
        if res is None:
            self._json(404, {"detail": "Prenotazione non trovata."})
            return
        res["status"] = "CANCELLED"
        self._json(200, _public(res))


def make_stub(host: str = "127.0.0.1", port: int = 0) -> tuple[ThreadingHTTPServer, str, StubState]:
    """Start the stub in a daemon thread. Returns ``(server, base_url, state)``."""
    state = StubState()
    handler = type("StubHandler", (Handler,), {"state": state})
    server = ThreadingHTTPServer((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}", state


def main(argv: list[str] | None = None) -> int:
    """``python stub_be.py [port]``: run the stub in the foreground."""
    import sys

    args = sys.argv[1:] if argv is None else argv
    try:
        port = int(args[0]) if args else 8000
    except ValueError:
        raise SystemExit("usage: python tests/stub_be.py [port]  (default 8000)") from None
    Handler.state = StubState()
    print(f"Stub BE on http://0.0.0.0:{port}  (Ctrl+C to stop)")
    try:
        ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
    except OSError as exc:
        raise SystemExit(f"port {port} is busy ({exc}): free it or pick another, e.g. python tests/stub_be.py 8001") from None
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
