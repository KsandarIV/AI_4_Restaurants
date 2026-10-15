"""Everything the bot says on its own (without the LLM), per language.

These are the same sentences the chat bot uses in its registration phase
(``chat/contatti.py`` + ``chat/api.py``), adapted to be *spoken*: short, no
markdown, phone numbers read digit by digit.

Code, logs and docs are in English; the *spoken* language follows
``VOICE_LANGUAGE`` (default ``it``: customers of the restaurant are Italian).
"""

from __future__ import annotations

from typing import Literal

Language = Literal["it", "en"]

_IT: dict[str, str] = {
    "welcome_register": (
        "Benvenuto alla Trattoria Bella Napoli! Per gestire le prenotazioni mi servono il suo "
        "nome e cognome e un numero di telefono. Può dirmeli insieme? Per esempio: Mario Rossi, "
        "tre tre tre, uno due tre, quattro cinque sei sette. Li usiamo solo per la sua prenotazione."
    ),
    "welcome_chat": (
        "Benvenuto alla Trattoria Bella Napoli! Come posso aiutarla? Posso prenotare, modificare "
        "o cancellare un tavolo, dirle il menu o darle informazioni sul locale."
    ),
    "contact_example": (
        "Mi servono nome e cognome e un numero di telefono, in un'unica frase. "
        "Per esempio: Mario Rossi, tre tre tre, uno due tre, quattro cinque sei sette."
    ),
    "problem_refusal": (
        "Capisco la preoccupazione: nome e telefono servono solo per confermare la prenotazione "
        "o avvisarla in caso di imprevisti."
    ),
    "problem_other": (
        "Prima di tutto mi servono i suoi dati di contatto, poi potrà chiedermi tutto quello che vuole."
    ),
    "problem_invalid_phone": "Il numero di telefono non sembra valido. Può ripeterlo cifra per cifra?",
    "problem_multiple_phones": "Ho sentito più numeri di telefono: quale devo usare per la prenotazione?",
    "problem_unclear_name": "Non sono sicuro di aver capito il nome: può dirmi nome e cognome?",
    "only_phone_missing": "Grazie {name}! Mi manca solo il numero di telefono.",
    "only_name_missing": "Ho il numero {phone}. Mi manca solo il nome.",
    "summary": "Ho capito: {name}, telefono {phone}. È corretto? Risponda sì o no.",
    "registering": "Perfetto, grazie {name}! Registro i suoi dati.",
    "restart": "Nessun problema, ricominciamo.",
    "yes_or_no": "Non ho capito: i dati sono corretti? Risponda sì o no.",
    "gave_up": (
        "Senza questi dati non posso gestire le prenotazioni, ma posso comunque rispondere a "
        "domande su menu, orari e informazioni sul locale. Come posso aiutarla?"
    ),
    "registered": (
        "Grazie {name}! Registrazione completata. Come posso aiutarla? Posso prenotare, modificare "
        "o cancellare un tavolo, dirle il menu o darle informazioni sul locale."
    ),
    "register_failed": "{error} Quando vuole, dica sì per riprovare.",
    "err_unreachable": "Non riesco a raggiungere il server. Controlli che il sistema sia acceso.",
    "err_slow": "Il server ci sta mettendo troppo a rispondere. Riprovi tra poco.",
    "err_llm_down": "Il modello linguistico non risponde in questo momento. Riprovi tra poco.",
    "err_server": "Il server ha avuto un problema. Riprovi tra poco.",
    "err_registration_unsupported": "Il server non supporta ancora la registrazione dei clienti.",
    "err_registration_rejected": "Il server ha rifiutato la registrazione.",
    "didnt_hear": "Non ho sentito bene, può ripetere?",
    "digit_sep": ", ",
    "plus": "più",
}

_EN: dict[str, str] = {
    "welcome_register": (
        "Welcome to Trattoria Bella Napoli! To manage bookings I need your first and last name and "
        "a phone number. Can you tell me both together? For example: Mario Rossi, three three three, "
        "one two three, four five six seven. I only use them for your booking."
    ),
    "welcome_chat": (
        "Welcome to Trattoria Bella Napoli! How can I help? I can book, change or cancel a table, "
        "tell you the menu or give you information about the restaurant."
    ),
    "contact_example": (
        "I need your first and last name and a phone number, in one sentence. "
        "For example: Mario Rossi, three three three, one two three, four five six seven."
    ),
    "problem_refusal": (
        "I understand the concern: name and phone are only used to confirm the booking "
        "or to warn you if something changes."
    ),
    "problem_other": "First I need your contact details, then you can ask me anything you like.",
    "problem_invalid_phone": "That phone number does not look valid. Can you repeat it digit by digit?",
    "problem_multiple_phones": "I heard more than one phone number: which one should I use for the booking?",
    "problem_unclear_name": "I am not sure I got the name: can you tell me your first and last name?",
    "only_phone_missing": "Thank you {name}! I only need the phone number now.",
    "only_name_missing": "I have the number {phone}. I only need the name now.",
    "summary": "I understood: {name}, phone {phone}. Is that correct? Please answer yes or no.",
    "registering": "Perfect, thank you {name}! I am saving your details.",
    "restart": "No problem, let's start again.",
    "yes_or_no": "I did not understand: are the details correct? Please answer yes or no.",
    "gave_up": (
        "Without these details I cannot manage bookings, but I can still answer questions about "
        "the menu, opening hours and the restaurant. How can I help?"
    ),
    "registered": (
        "Thank you {name}! Registration complete. How can I help? I can book, change or cancel a "
        "table, tell you the menu or give you information about the restaurant."
    ),
    "register_failed": "{error} Whenever you want, say yes to try again.",
    "err_unreachable": "I cannot reach the server. Please check that the system is running.",
    "err_slow": "The server is taking too long to answer. Please try again shortly.",
    "err_llm_down": "The language model is not answering right now. Please try again shortly.",
    "err_server": "The server had a problem. Please try again shortly.",
    "err_registration_unsupported": "The server does not support customer registration yet.",
    "err_registration_rejected": "The server rejected the registration.",
    "didnt_hear": "I did not hear that well, could you repeat?",
    "digit_sep": ", ",
    "plus": "plus",
}

_CATALOG: dict[str, dict[str, str]] = {"it": _IT, "en": _EN}


def normalize_language(value: str) -> Language:
    """Map any ``it-IT`` / ``EN`` style code onto a supported language (default ``it``)."""
    return "en" if value.strip().lower().startswith("en") else "it"


def say(language: str, key: str, **fields: str) -> str:
    """Return the localized sentence ``key`` formatted with ``fields``."""
    catalog = _CATALOG[normalize_language(language)]
    return catalog[key].format(**fields) if fields else catalog[key]
