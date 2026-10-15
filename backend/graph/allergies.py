"""Answers about allergies and intolerances, written by code from the menu in the database.

A language model must never improvise on this topic: tests with small models showed it inventing dishes that
are not on the menu and calling them "allergen free". So these questions do NOT go through the LLM.
"""
import re
from typing import List, Optional

from backend.database import crud
from backend.database.connection import SessionLocal

# The customer talks about an allergy / intolerance / "without X"
_TRIGGER = re.compile(
    r"allerg|intoller|celiac|senza\s+(?:glutin|lattosio|latticin|uov|pesce|molluschi|solfit)|"
    r"non\s+(?:posso|devo)\s+(?:mangiare|assumere)", re.I)
# ...unless he is booking (then the LLM handles it: it goes in the special requests)
_BOOKING = re.compile(r"prenot|tavol|riserv|persone|posti", re.I)

# What the customer writes -> the allergen name used in the menu
_ALLERGEN_PATTERNS = [
    (re.compile(r"glutin|celiac|frument", re.I), "glutine"),
    (re.compile(r"lattosio|latticin|\blatte\b|formagg", re.I), "lattosio"),
    (re.compile(r"\buov[ao]\b", re.I), "uova"),
    (re.compile(r"molluschi|frutti di mare|vongol|cozz", re.I), "molluschi"),
    (re.compile(r"\bpesce\b", re.I), "pesce"),
    (re.compile(r"solfit", re.I), "solfiti"),
]

_ADVICE = ("Segnali sempre la sua allergia o intolleranza al personale di sala: in cucina verificheranno gli ingredienti "
           "e l'eventuale contaminazione. Se ha altre allergie non elencate nel menu, le comunichi allo staff.")


def _known_allergens() -> List[str]:
    with SessionLocal() as db:
        return sorted({a.strip().lower() for (allergens,) in db.query(crud.MenuItem.allergens).all()
                       for a in (allergens or "").split(",") if a.strip()})


def answer_allergy_question(message: str, client_type: str = "chat") -> Optional[str]:
    """The reply to an allergy/intolerance question, or None if the message is something else."""
    if not _TRIGGER.search(message) or _BOOKING.search(message):
        return None

    wanted = [name for pattern, name in _ALLERGEN_PATTERNS if pattern.search(message)]
    if not wanted:
        known = ", ".join(_known_allergens())
        return f"Non ho informazioni su quell'allergene: nel nostro menu sono indicati {known}. {_ADVICE}"

    with SessionLocal() as db:
        safe = None
        for allergen in wanted:
            names = {i["id"]: i for i in crud.get_menu_items(db, allergen_free=allergen)}
            safe = names if safe is None else {k: v for k, v in safe.items() if k in names}
    label = " e ".join(wanted)
    if not safe:
        return f"Nel nostro menu non ci sono piatti senza {label}. {_ADVICE}"

    if client_type == "voice":  # a voice reads sentences, not bullet lists
        return f"Senza {label} abbiamo: {', '.join(i['name'] for i in safe.values())}. {_ADVICE}"
    lines = [f"- {i['name']} (€{i['price']:.2f})" for i in safe.values()]
    return f"Ecco i piatti del nostro menu senza {label}:\n" + "\n".join(lines) + f"\n\n{_ADVICE}"
