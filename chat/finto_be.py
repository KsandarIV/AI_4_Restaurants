"""BE finto per provare il chatbot senza il BE vero. Nessuna dipendenza esterna.

Avvio:  python finto_be.py [porta]  (predefinita 8000: http://localhost:8000)
Imita il contratto del BE: POST /api/customers (proposto, non ancora nel BE vero),
POST /api/chat e GET /api/health.
"""
import json
import sys
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

CLIENTI = {}  # customer_id -> {"name", "phone"}: nel BE vero starebbe in una tabella del database


class Handler(BaseHTTPRequestHandler):
    def _rispondi(self, codice, corpo):
        dati = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(codice)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dati)))
        self.end_headers()
        self.wfile.write(dati)

    def _leggi_json(self):
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))

    def do_GET(self):
        if self.path == "/api/health":
            self._rispondi(200, {"status": "ok", "llm_provider": "finto", "clienti_registrati": len(CLIENTI)})
        else:
            self._rispondi(404, {"detail": "Not Found"})

    def do_POST(self):
        if self.path == "/api/customers":
            return self._registra_cliente()
        if self.path == "/api/chat":
            return self._chat()
        self._rispondi(404, {"detail": "Not Found"})

    def _registra_cliente(self):
        try:
            richiesta = self._leggi_json()
            nome, telefono, consenso = richiesta["name"], richiesta["phone"], richiesta["consent"]
        except (ValueError, KeyError):
            return self._rispondi(422, {"detail": "name, phone e consent sono obbligatori"})
        if not nome.strip() or not telefono.startswith("+") or consenso is not True:
            return self._rispondi(422, {"detail": "dati non validi"})
        customer_id = f"cust_{uuid.uuid4().hex[:8]}"
        CLIENTI[customer_id] = {"name": nome, "phone": telefono}
        print(f"[finto BE] cliente registrato: {customer_id}")  # nome e telefono non si stampano
        self._rispondi(200, {"customer_id": customer_id})

    def _chat(self):
        try:
            richiesta = self._leggi_json()
            messaggio, sessione = richiesta["message"], richiesta["session_id"]
        except (ValueError, KeyError):
            return self._rispondi(422, {"detail": "message e session_id sono obbligatori"})

        risposta = f"[BE finto] Ho ricevuto: «{messaggio}»."
        if "prenot" in messaggio.lower():
            risposta += " Prenotazione confermata! Codice: RES-TEST01."
        self._rispondi(200, {
            "reply": risposta,
            "session_id": sessione,
            "customer_id": richiesta.get("customer_id") or f"anon_{sessione}",
            "client_type": richiesta.get("client_type", "chat"),
            "timestamp": "2026-01-01T00:00:00Z",
        })


if __name__ == "__main__":
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"BE finto su http://localhost:{porta}  (Ctrl+C per fermare)")
    HTTPServer(("0.0.0.0", porta), Handler).serve_forever()
