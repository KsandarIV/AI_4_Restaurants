"""Collect the caller's name and phone number, by voice, in one utterance.

Port of ``chat/contatti.py`` (same dialogue: ask -> read back -> confirm) with the
changes speech needs:

* STT writes spoken digits in several ways ("tre tre tre", "333, 123, 4567",
  "più 39 333..."), so the text is normalised before the phone number is parsed;
* the read-back says the phone number digit by digit, so the TTS does not read it
  as one huge number;
* sentences exist in Italian and English (``messages.py``) and so do the
  trigger phrases ("mi chiamo" / "my name is", "sì" / "yes").

No network and no LLM here: nothing said in this phase ever reaches the model.
The data only goes to ``POST /api/customers`` (see ``conversation.py``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import phonenumbers

from .messages import normalize_language, say

REGION = "IT"  # numbers spoken without a country prefix are Italian
MAX_ATTEMPTS = 3  # consecutive turns with no new data before giving up

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_GREETINGS = re.compile(
    r"\b(?:ciao|salve|buongiorno|buonasera|buon pomeriggio|hello|hi|hey|"
    r"good (?:morning|afternoon|evening))\b",
    re.I,
)
# Longer phrases first ("a nome di" before "nome").
_PHONE_PHRASES = re.compile(
    r"\b(?:il mio numero di telefono è|il mio numero è|il mio numero|numero di telefono|numero|"
    r"telefono|cellulare|cell|tel|recapito|my phone number is|my number is|my number|"
    r"phone number|phone|mobile|cell)\b\.?",
    re.I,
)
_NAME_PHRASES = re.compile(
    r"\b(?:mi chiamo|il mio nome è|il mio nome|nome e cognome|a nome di|a nome|nome|cognome|sono|"
    r"my name is|my name|my first and last name is|first and last name|under the name of|"
    r"under the name|this is|i am|i['’]m|name|surname|last name|first name)\b",
    re.I,
)
# Only conjunctions: articles like "la" / "di" can be part of a surname (La Rosa, Di Maio).
_CONJUNCTIONS = re.compile(r"\b(?:e|è|ed|o|oppure|and|or|is)\b", re.I)
_REFUSAL = re.compile(
    r"\b(?:non voglio|preferisco non|non intendo|non posso dare|no grazie|privacy|"
    r"perch[eé] (?:servono|devo|dovrei)|i do(?: not|n['’]t) want|i prefer not|no thanks|"
    r"why do you need)\b",
    re.I,
)
# Words that make an utterance a question/sentence, not a name.
_NOT_NAMES = {
    "vorrei", "voglio", "vorremmo", "prenotare", "prenotazione", "tavolo", "menu", "avete", "siete",
    "quanto", "quando", "dove", "come", "perché", "perche", "cosa", "che", "per", "con", "non",
    "grazie", "persone", "orario", "domani", "oggi", "stasera", "posso", "potete", "informazioni",
    "aiuto", "privacy", "si", "sì", "no", "ok",
    "want", "would", "like", "book", "booking", "table", "reserve", "reservation", "can", "could",
    "what", "when", "where", "how", "why", "please", "thanks", "thank", "yes", "okay", "tonight",
    "tomorrow", "today", "people", "opening", "hours", "help",
}
_YES = re.compile(
    r"^\W*(?:s[ìi]|ok|okay|certo|corretto|esatto|esattamente|giusto|perfetto|confermo|va bene|"
    r"assolutamente|yes|yeah|yep|sure|correct|right|exactly|perfect|confirm|that['’]s right)\b",
    re.I,
)
_NO = re.compile(
    r"^\W*(?:no|nope|sbagliato|errato|non è corretto|non e corretto|wrong|incorrect|not correct)\b",
    re.I,
)

_DIGIT_WORDS = {
    "zero": "0", "uno": "1", "una": "1", "due": "2", "tre": "3", "quattro": "4", "cinque": "5",
    "sei": "6", "sette": "7", "otto": "8", "nove": "9",
    "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9",
}
_WORD_RUN = re.compile(
    r"\b(?:" + "|".join(_DIGIT_WORDS) + r")(?:[\s,.-]+(?:" + "|".join(_DIGIT_WORDS) + r")\b)+",
    re.I,
)
_PLUS = re.compile(r"\b(?:più|plus)\s*(?=\d)", re.I)
_DIGIT_RUN = re.compile(r"(?<![\w+])\+?\d(?:[\s,.\-]{0,2}\d){8,13}(?!\d)")


def normalize_spoken_numbers(text: str) -> str:
    """Rewrite spoken digits as digits so the phone parser can see them.

    * runs of 3+ digit words  -> "tre tre tre uno due tre" -> "333123"
    * "più 39 ..." / "plus 39 ..." -> "+39 ..."
    * 9-14 digits split by spaces/commas/dots -> one compact digit string
    """

    def _words(match: re.Match[str]) -> str:
        parts = re.findall(r"[^\s,.\-]+", match.group())
        return "".join(_DIGIT_WORDS[p.lower()] for p in parts) if len(parts) >= 3 else match.group()

    text = _WORD_RUN.sub(_words, text)
    text = _PLUS.sub("+", text)
    return _DIGIT_RUN.sub(lambda m: ("+" if m.group().startswith("+") else "") + re.sub(r"\D", "", m.group()), text)


def phone_for_speech(e164: str, language: str = "it") -> str:
    """Read a phone number digit by digit: '+393331234567' -> '3 3 3, 1 2 3, 4 5 6 7'."""
    try:
        parsed = phonenumbers.parse(e164)
    except phonenumbers.NumberParseException:
        return " ".join(re.sub(r"\D", "", e164))
    digits = str(parsed.national_number)
    if parsed.country_code == 39:  # the caller is Italian: skip the obvious prefix
        groups = [digits[:3], digits[3:6], digits[6:]]
        prefix = ""
    else:
        groups = [digits[i : i + 3] for i in range(0, len(digits), 3)]
        prefix = say(language, "plus") + " " + " ".join(str(parsed.country_code)) + ", "
    sep = say(language, "digit_sep")
    return prefix + sep.join(" ".join(g) for g in groups if g)


@dataclass
class Contacts:
    """What could be extracted from one utterance."""

    name: str | None = None
    phone: str | None = None  # E.164, e.g. "+393331234567"
    # Possible values: refusal, other, invalid_phone, multiple_phones, unclear_name
    problems: list[str] = field(default_factory=list)


def _format_name(token: str) -> str:
    return token.title() if token.islower() or token.isupper() else token


def extract_contacts(text: str) -> Contacts:
    """Extract name and phone number from a free-form utterance."""
    result = Contacts()
    rest = normalize_spoken_numbers(text.strip())

    # --- Phone: found and validated by the phonenumbers library ---
    found: dict[str, tuple[int, int]] = {}  # E.164 -> (start, end)
    for match in phonenumbers.PhoneNumberMatcher(rest, REGION):
        e164 = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)
        found[e164] = (match.start, match.end)
    for start, end in sorted(found.values(), reverse=True):  # from the end: keep offsets valid
        rest = rest[:start] + " " + rest[end:]
    if len(found) == 1:
        result.phone = next(iter(found))
    elif len(found) > 1:
        result.problems.append("multiple_phones")
    elif re.search(r"\+?\d[\d\s.\-()/]{2,}\d", rest):  # something number-like, but not valid
        result.problems.append("invalid_phone")

    # --- Name: what is left after removing phone, e-mail and filler phrases ---
    rest = _EMAIL.sub(" ", rest)
    rest = re.sub(r"\d+", " ", rest)
    for rule in (_GREETINGS, _PHONE_PHRASES, _NAME_PHRASES, _CONJUNCTIONS):
        rest = rule.sub(" ", rest)
    words = re.findall(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*", rest)  # letters, inner apostrophes/hyphens
    words = [w for w in words if len(w) > 1]  # initials ("M.") are dropped

    if words:
        if "?" in text or {w.lower() for w in words} & _NOT_NAMES:
            result.problems.append("other")
        elif len(words) > 4:
            result.problems.append("unclear_name")
        else:
            result.name = " ".join(_format_name(w) for w in words)

    if not result.name and not result.phone and _REFUSAL.search(text):
        result.problems = ["refusal"]  # "non voglio..." contains "non" but is a refusal, not a question
    return result


_PROBLEM_KEYS = {
    "refusal": "problem_refusal",
    "other": "problem_other",
    "invalid_phone": "problem_invalid_phone",
    "multiple_phones": "problem_multiple_phones",
    "unclear_name": "problem_unclear_name",
}


class RegistrationDialog:
    """Registration dialogue. Phases: collecting -> confirming -> done | gave_up.

    ``handle(text)`` returns ``(reply, action)``. The action tells the caller what
    to do: ``"register"`` = send name and phone to the BE; ``"give_up"`` = continue
    without registration (anonymous customer id); ``None`` = keep talking.
    """

    def __init__(self, language: str = "it") -> None:
        self.language = normalize_language(language)
        self.phase = "collecting"
        self.name: str | None = None
        self.phone: str | None = None
        self.attempts = 0

    def opening(self) -> str:
        """The first thing the bot says."""
        return say(self.language, "welcome_register")

    def handle(self, text: str) -> tuple[str, str | None]:
        """Process one utterance of the registration phase."""
        return self._confirm(text) if self.phase == "confirming" else self._collect(text)

    def retry_confirmation(self) -> None:
        """After a failed registration call: the data stays, a new "yes" retries."""
        self.phase = "confirming"

    # -- internals --

    def _collect(self, text: str) -> tuple[str, str | None]:
        contacts = extract_contacts(text)
        progress = self._update(contacts, text)
        if self.name and self.phone:
            self.phase = "confirming"
            return self._summary(), None
        if not progress:
            self.attempts += 1
            if self.attempts >= MAX_ATTEMPTS:
                self.phase = "gave_up"
                return say(self.language, "gave_up"), "give_up"
        return self._ask_missing(contacts.problems), None

    def _confirm(self, text: str) -> tuple[str, str | None]:
        if _YES.match(text):
            self.phase = "done"
            return say(self.language, "registering", name=self.name or ""), "register"
        contacts = extract_contacts(text)
        if self._update(contacts, text):  # a correction, even after a "no"
            return self._summary(), None
        if _NO.match(text):
            self.name = self.phone = None
            self.phase = "collecting"
            return say(self.language, "restart") + " " + say(self.language, "contact_example"), None
        return say(self.language, "yes_or_no"), None

    def _update(self, contacts: Contacts, text: str) -> bool:
        """Store new or corrected data; True when something changed.

        When a name is already stored, a single word ("mah", "boh") does not replace it:
        it takes a name of two words or an explicit "no" / "mi chiamo".
        """
        changed = False
        name = contacts.name
        if name and self.name and name != self.name:
            if len(name.split()) < 2 and not (_NO.match(text) or _NAME_PHRASES.search(text)):
                name = None
        if name and name != self.name:
            self.name, changed = name, True
        if contacts.phone and contacts.phone != self.phone:
            self.phone, changed = contacts.phone, True
        return changed

    def _summary(self) -> str:
        assert self.name and self.phone
        return say(
            self.language, "summary",
            name=self.name, phone=phone_for_speech(self.phone, self.language),
        )

    def _ask_missing(self, problems: list[str]) -> str:
        lines = [say(self.language, _PROBLEM_KEYS[p]) for p in problems if p in _PROBLEM_KEYS]
        if self.name and not self.phone:
            lines.append(say(self.language, "only_phone_missing", name=self.name))
        elif self.phone and not self.name:
            lines.append(
                say(self.language, "only_name_missing", phone=phone_for_speech(self.phone, self.language))
            )
        else:
            lines.append(say(self.language, "contact_example"))
        return " ".join(lines)
