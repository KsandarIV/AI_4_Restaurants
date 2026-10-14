"""BE finto per provare il chatbot senza il BE vero. Nessuna dipendenza esterna.

Avvio:  python finto_be.py          (ascolta su http://localhost:8000)
Imita il contratto del BE vero: POST /api/chat e GET /api/health.
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def _rispondi(self, codice, corpo):
        dati = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(codice)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dati)))
        self.end_headers()
        self.wfile.write(dati)

    def do_GET(self):
        if self.path == "/api/health":
            self._rispondi(200, {"status": "ok", "llm_provider": "finto"})
        else:
            self._rispondi(404, {"detail": "Not Found"})

    def do_POST(self):
        if self.path != "/api/chat":
            return self._rispondi(404, {"detail": "Not Found"})
        try:
            richiesta = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
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
    print("BE finto su http://localhost:8000  (Ctrl+C per fermare)")
    HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
