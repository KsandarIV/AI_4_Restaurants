"""Remove personal data from the text *before* it is sent to the BE.

Port of ``chat/anonimizzatore.py`` so both bots behave identically. Layers, in order:

1. regexes for fixed-shape data (e-mail, fiscal code, phone, street address);
2. regexes for phrases that introduce a name ("a nome di Rossi", "my name is ...");
3. the local spaCy NER model, as a safety net for other person names. It is
   optional: if spaCy or ``it_core_news_md`` is missing, layers 1-2 still run.

Placeholders keep the chat bot's exact format ``[TYPE_N]`` (``[NOME_1]``,
``[TELEFONO_1]``...): the BE recognises that shape (``backend/graph/workflow.py``)
and the replies are restored with ``restore()`` so the customer hears real names.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from .logging_json import get_logger

log = get_logger("anonymizer")

# ORDER MATTERS: e-mail before phone, because an address can contain digits.
RULES: list[tuple[str, str]] = [
    ("EMAIL", r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    # Fiscal code: 6 letters, 2 digits, 1 letter, 2 digits, 1 letter, 3 digits, 1 letter
    ("CODICE_FISCALE", r"\b[A-Za-z]{6}\d{2}[A-Za-z]\d{2}[A-Za-z]\d{3}[A-Za-z]\b"),
    # Phone: optional +39/0039, then mobile (3xx) or landline (0x...). Dates (12/05/2025)
    # are untouched: they contain "/" and do not start with 3xx or 0x.
    ("TELEFONO", r"(?<![\w/])(?:(?:\+|00)39[\s.-]?)?(?:3\d{2}|0\d{1,3})[\s.-]?\d{3}[\s.-]?\d{3,4}(?![\w/])"),
    # Street address: "via Garibaldi 12", "piazza San Marco 3b"
    ("INDIRIZZO", r"(?i:\b(?:via|viale|piazza|corso|largo|vicolo)\s+[a-zàèéìòù' .]+?\s+\d{1,4}[a-z]?\b)"),
]

# Name-introducing phrases (trigger is case-insensitive, the name must be capitalised).
_NAME = r"[A-ZÀ-Ý][\w'’-]*(?:\s+[A-ZÀ-Ý][\w'’-]*)*"
NAME_PHRASES = re.compile(
    r"(?i:\b(?:a nome(?: di)?|mi chiamo|sono|intestata a|intestato a|prenotazione di|"
    r"my name is|i am|i['’]m|under the name(?: of)?|booking for|reservation for))\s+(" + _NAME + ")"
)

# The NER sometimes mistakes greetings for names: never anonymise these.
NOT_NAMES = {"buongiorno", "buonasera", "buonanotte", "salve", "ciao", "grazie", "arrivederci",
             "hello", "thanks"}

_SPACY_MODEL = "it_core_news_md"
_nlp: Any = None
_nlp_failed = False


def _load_model() -> Any | None:
    """Load spaCy once; return None (and remember it) when unavailable."""
    global _nlp, _nlp_failed
    if _nlp is None and not _nlp_failed:
        try:
            import spacy

            _nlp = spacy.load(_SPACY_MODEL, disable=["lemmatizer", "parser"])
        except Exception as exc:  # ImportError, OSError (model missing), ...
            _nlp_failed = True
            log.warning("spaCy NER unavailable (%s): using regex layers only", type(exc).__name__)
    return _nlp


def ner_available() -> bool:
    """True when the NER safety net can run (loads the model if needed)."""
    return _load_model() is not None


class Anonymizer:
    """Replace personal data with placeholders and remember what they stand for.

    Example: "sono Mario Rossi, 333 1234567" -> "sono [NOME_1], [TELEFONO_1]".
    The same value always gets the same placeholder. One instance per conversation.
    """

    def __init__(self, use_model: bool | None = None) -> None:
        self.mapping: dict[str, str] = {}  # placeholder -> real value
        self._use_model = use_model  # None = use the NER when it is installed

    def anonymize(self, text: str) -> str:
        """Return ``text`` with personal data replaced by placeholders."""
        for kind, regex in RULES:
            text = re.sub(regex, self._replacer(kind), text)
        text = NAME_PHRASES.sub(
            lambda m: m.group().replace(m.group(1), self._placeholder("NOME", m.group(1))), text
        )
        if self._use_model is not False:
            text = self._names_with_model(text)
        return text

    def restore(self, text: str) -> str:
        """Put the real values back in place of the placeholders (BE replies)."""
        for placeholder, value in self.mapping.items():
            text = text.replace(placeholder, value)
        return text

    def stream_restorer(self) -> StreamRestorer:
        """A restorer for token streams (a placeholder may arrive split across tokens)."""
        return StreamRestorer(self)

    def _replacer(self, kind: str) -> Callable[[re.Match[str]], str]:
        def replace(match: re.Match[str]) -> str:
            return self._placeholder(kind, match.group())

        return replace

    def _names_with_model(self, text: str) -> str:
        nlp = _load_model()
        if nlp is None:
            return text
        entities = [
            e for e in nlp(text).ents
            if e.label_ == "PER" and "[" not in e.text and e.text.lower() not in NOT_NAMES
        ]
        # Placeholders are numbered in reading order, but inserted from the end so
        # the earlier offsets stay valid.
        replacements = [(e.start_char, e.end_char, self._placeholder("NOME", e.text)) for e in entities]
        for start, end, placeholder in reversed(replacements):
            text = text[:start] + placeholder + text[end:]
        return text

    def _placeholder(self, kind: str, value: str) -> str:
        for placeholder, existing in self.mapping.items():
            if existing == value:
                return placeholder
        number = sum(1 for p in self.mapping if p.startswith(f"[{kind}_")) + 1
        placeholder = f"[{kind}_{number}]"
        self.mapping[placeholder] = value
        return placeholder


class StreamRestorer:
    """Restore placeholders in a token stream without ever speaking half of one.

    A token ending in ``[NOM`` is held back until the closing ``]`` arrives
    (or until it is clearly not a placeholder), then released restored.
    """

    _MAX_HOLD = 24  # longest possible placeholder: "[CODICE_FISCALE_12]"

    def __init__(self, anonymizer: Anonymizer) -> None:
        self._anonymizer = anonymizer
        self._held = ""

    def feed(self, token: str) -> str:
        """Add a token; return the text that is safe to speak now."""
        text = self._held + token
        cut = text.rfind("[")
        if cut != -1 and "]" not in text[cut:] and len(text) - cut <= self._MAX_HOLD:
            self._held = text[cut:]
            text = text[:cut]
        else:
            self._held = ""
        return self._anonymizer.restore(text)

    def flush(self) -> str:
        """Release anything still held at the end of the stream."""
        text, self._held = self._held, ""
        return self._anonymizer.restore(text)
