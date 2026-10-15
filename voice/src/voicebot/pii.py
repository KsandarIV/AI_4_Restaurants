"""Last-line PII safety net for the transport layer.

The real anonymisation happens in ``conversation.py`` with :class:`Anonymizer`
(same rules as the chat bot, restorable placeholders). ``scrub_pii`` runs the same
regex layers once more, statelessly and without the NER model, on whatever is about
to leave for the BE - so a future code path that forgets to anonymise still cannot
leak an e-mail address or a phone number.
"""

from __future__ import annotations

from .anonymizer import Anonymizer


def scrub_pii(text: str) -> str:
    """Replace e-mails, fiscal codes, phone numbers and addresses with ``[TYPE_N]`` tags."""
    return Anonymizer(use_model=False).anonymize(text)
