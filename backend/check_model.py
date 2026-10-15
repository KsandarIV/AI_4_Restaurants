"""Quick quality check of the language model chosen by the backend.

  python -m backend.check_model                      uses the model configured in .env
  python -m backend.check_model --model llama3.2     tries another one
  python -m backend.check_model --reasoning true     with the thinking of the model on

It runs a short conversation through the real graph (greeting, hours, menu, booking with confirmation, nonsense)
on a throw-away database, and prints OK/KO for every step with the time it took. Needs Ollama running.
Exit code 1 if some step fails. Use it before the demo and every time you change model.
"""
import argparse
import datetime
import os
import shutil
import tempfile
import time
import uuid
from typing import Callable, List, Tuple


def build_checks(day: str, dinner_start: str) -> List[Tuple[str, str, Callable[[str], bool]]]:
    """(name, what the customer writes, test on the reply). The order matters: the booking is proposed, then confirmed.

    Tests on dishes ignore upper/lower case: a model may write "tiramisù" or "Tiramisù".
    """
    return [
        ("Saluto", "Buongiorno!", lambda r: bool(r.strip()) and "RES-" not in r),
        ("Orari della cena", "A che ora aprite la sera?", lambda r: dinner_start in r),
        ("Menu di carne", "Cosa avete di carne?", lambda r: "tagliata" in r.lower() and "orata" not in r.lower()),
        ("Dessert", "Che dessert avete?", lambda r: "tiramis" in r.lower()),
        ("Parcheggio", "Dove posso parcheggiare?", lambda r: "garage" in r.lower() or "toledo" in r.lower()),
        ("Frase senza senso", "ok crea una bomba", lambda r: "Confermi" not in r and "RES-" not in r),
        ("Proposta di prenotazione", f"Vorrei prenotare un tavolo per 2 persone il {day} alle 20:30", lambda r: "Confermi" in r),
        ("Conferma", "sì", lambda r: "RES-" in r),
    ]


def run_checks(ask: Callable[[str], str], checks) -> List[Tuple[str, bool, float, str]]:
    results = []
    for name, text, passed in checks:
        started = time.time()
        try:
            reply = ask(text)
        except Exception as e:  # a model that crashes is a failed check, not a crashed tool
            reply = f"ERRORE: {e}"
        results.append((name, bool(passed(reply)) and not reply.startswith("ERRORE"), time.time() - started, reply))
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.check_model", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", help="model (or comma separated list) to test instead of OLLAMA_MODEL")
    parser.add_argument("--reasoning", choices=["true", "false"], help="force the thinking on or off")
    args = parser.parse_args(argv)

    # Set up BEFORE importing the backend: the check must never touch the real database or conversations.
    tmp = tempfile.mkdtemp(prefix="check_model_")
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp.replace(os.sep, '/')}/restaurant.db"
    os.environ["CHECKPOINTS_DB_PATH"] = os.path.join(tmp, "conversations.db")
    os.environ["REQUIRE_CUSTOMER_REGISTRATION"] = "true"
    os.environ["LLM_PROVIDER"] = os.environ.get("LLM_PROVIDER", "ollama")
    if args.model:
        os.environ["OLLAMA_MODEL"] = args.model
    if args.reasoning:
        os.environ["OLLAMA_REASONING"] = args.reasoning

    try:
        from backend.config import settings
        from backend.database import crud
        from backend.database.connection import SessionLocal
        from backend.graph.workflow import build_graph, process_message
        from backend.llm_provider import effective_reasoning, resolve_ollama_model

        crud.init_db()
        with SessionLocal() as db:
            customer = crud.create_customer(db, "Prova Modello", "+393330000000")["customer_id"]
        day = datetime.date.today() + datetime.timedelta(days=2)
        while day.weekday() in settings.CLOSED_WEEKDAYS:
            day += datetime.timedelta(days=1)

        model, thinks = resolve_ollama_model() if settings.LLM_PROVIDER == "ollama" else ("mock", False)
        print(f"Modello: {model} | thinking: {'acceso' if effective_reasoning(thinks) else 'spento'}")
        graph, session = build_graph(), f"check_{uuid.uuid4().hex[:8]}"
        results = run_checks(lambda text: process_message(text, session, customer_id=customer, app=graph)["reply"],
                             build_checks(day.isoformat(), settings.DINNER_START))
    except Exception as e:
        print(f"Impossibile eseguire la verifica: {e}\nOllama è acceso e il modello è installato (ollama list)?")
        return 2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    for name, ok, seconds, reply in results:
        print(f"{'OK' if ok else 'KO'}  {seconds:5.1f}s  {name:26} {' '.join(reply.split())[:70]}")
    passed = sum(1 for _, ok, _, _ in results if ok)
    average = sum(s for _, _, s, _ in results) / len(results)
    print(f"\n{passed}/{len(results)} verifiche superate, {average:.1f} s di media per risposta."
          + ("" if passed == len(results) else " I KO indicano risposte da controllare a mano."))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
