"""Catch replies in which the LLM talks about its tools instead of using them.

A small local model sometimes answers "Per vedere il menu devo prima chiamare get_menu. Vuole che verifichi?"
instead of calling the tool. A caller must never hear that: the reply is dropped and the turn is retried once
with an instruction (``NUDGE``), then, if it happens again, replaced by a neutral sentence.

Only the *shape* of the text is checked (snake_case tool names, "I must call...", "do you want me to check...?"):
no intent detection, no content is inspected beyond that.
"""

from __future__ import annotations

import re

# Appended to the caller's (already anonymised) message on the single retry.
NUDGE = (
    "\n(Usa subito gli strumenti che ti servono, senza nominarli e senza chiedere il permesso: "
    "rispondi solo con il risultato.)"
)

_TOOL_TALK = re.compile(
    r"\b[a-z]+(?:_[a-z]+)+\b"  # get_menu, check_availability, ...
    r"|\bdevo prima (?:chiamare|usare|consultare|verificare|controllare)\b"
    r"|\b(?:chiamo|chiamare|richiamo|uso|usare) (?:lo strumento|la funzione|il tool)\b"
    r"|\bvuole che (?:io )?(?:verifichi|controlli|consulti|cerchi|guardi|le mostri|legga)\b"
    r"|\b(?:strumento|strumenti|tool)\b"
    r"|\bI (?:need|have) to call\b|\bdo you want me to (?:check|look)\b"
    # "I can show you the menu" / "I can give you the address" instead of showing it or giving it
    r"|\bposso (?:(?:mostrar|fornir|elencar|indicar|dir|dar)(?:le|ti)|controllare|verificare|consultare)\s+(?:subito\s+)?"
    r"(?:i|le|gli|il|l'|lo|la|un|una)\s*(?:piatti|menu|orari|orario|indirizzo|informazioni|disponibilit\w+|numero|telefono)",
    re.IGNORECASE,
)

_SENTENCE_END = re.compile(r"[.!?…]\s|[.!?…]$")


def leaks_tool_talk(text: str) -> bool:
    """True when the reply names a tool or asks a pointless permission to use one."""
    return bool(_TOOL_TALK.search(text))


def first_sentence_done(text: str) -> bool:
    """True once enough of the reply has arrived to judge it (a full sentence of some length - not just "Certamente." -
    or a long run without one)."""
    return (bool(_SENTENCE_END.search(text)) and len(text) >= 40) or len(text) >= 160
