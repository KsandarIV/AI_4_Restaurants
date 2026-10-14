"""PII scrubbing: CHAT/VOICE must pre-process data before sending to BE."""

from __future__ import annotations

import re

_EMAIL = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE = re.compile(r"(?<!\d)(?:\+?39[\s.-]?)?(?:\d[\s.-]?){9,10}(?!\d)")
_CCF = re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b", re.IGNORECASE)
_CARD = re.compile(r"\b(?:\d[ -]?){13,16}\b")


def scrub_pii(text: str) -> str:
    """Replace emails, phones, fiscal codes and card-like numbers with tags."""
    redacted = _EMAIL.sub("[EMAIL]", text)
    redacted = _CCF.sub("[CODICE_FISCALE]", redacted)
    redacted = _CARD.sub("[CARTA]", redacted)
    # Phone last: avoids clobbering dates already handled; keep short numbers (e.g. "2 persone", "ore 20") intact
    # by requiring at least 9 digits.
    digits_only = re.sub(r"\D", "", text)
    if len(digits_only) >= 9:
        redacted = _PHONE.sub("[TELEFONO]", redacted)
    return redacted
