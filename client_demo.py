"""
Script di esempio per testare la connessione al Backend via rete LAN.
Può essere utilizzato dai componenti CHAT (Membro 2) e VOICE (Membro 3) come riferimento.
"""

import sys
import uuid
import requests

def run_client(base_url="http://localhost:8000"):
    print(f"=== Connessione al Backend Ristorante su: {base_url} ===")

    # 1. Healthcheck
    try:
        health = requests.get(f"{base_url}/api/health", timeout=5).json()
        print(f"[OK] Backend attivo! Ristorante: {health['restaurant']} | LLM: {health['llm_model']}")
    except Exception as e:
        print(f"[ERRORE] Impossibile contattare il backend: {e}")
        return

    # Genera una session_id e un customer_id anonimo (Privacy Constraint #3)
    session_id = f"sess_{uuid.uuid4().hex[:8]}"
    customer_id = f"anon_{uuid.uuid4().hex[:6]}"

    print(f"\nSessione avviata: {session_id} (Cliente anonimizzato: {customer_id})")
    print("Scrivi un messaggio per interagire con l'assistente (oppure 'esci' per terminare):")

    while True:
        try:
            user_msg = input("\nTu > ").strip()
            if not user_msg:
                continue
            if user_msg.lower() in ["esci", "exit", "quit"]:
                print("Chiusura del client.")
                break

            payload = {
                "message": user_msg,
                "session_id": session_id,
                "customer_id": customer_id,
                "client_type": "chat"  # o "voice"
            }

            resp = requests.post(f"{base_url}/api/chat", json=payload, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                print(f"\nAssistente AI > {data['reply']}")
            else:
                print(f"\n[ERRORE {resp.status_code}] {resp.text}")

        except KeyboardInterrupt:
            print("\nInterrotto.")
            break
        except Exception as e:
            print(f"\nErrore nella chiamata: {e}")

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    run_client(url)
