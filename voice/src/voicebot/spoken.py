"""Turn numbers, dates and times into words a TTS reads naturally (Italian and English).

Piper reads "20:30" or "2026-10-16" badly (or digit by digit). The final report of a booking is
built from the BE's data by code, so it is formatted here, once, instead of trusting the LLM.
"""

from __future__ import annotations

import datetime as dt

from .messages import normalize_language

_IT_UNITS = ["zero", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove", "dieci",
             "undici", "dodici", "tredici", "quattordici", "quindici", "sedici", "diciassette",
             "diciotto", "diciannove"]
_IT_TENS = {2: "venti", 3: "trenta", 4: "quaranta", 5: "cinquanta", 6: "sessanta", 7: "settanta",
            8: "ottanta", 9: "novanta"}
_IT_WEEKDAYS = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
_IT_MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
              "settembre", "ottobre", "novembre", "dicembre"]

_EN_UNITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
             "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
             "eighteen", "nineteen"]
_EN_TENS = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty", 7: "seventy",
            8: "eighty", 9: "ninety"}
_EN_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
              "October", "November", "December"]
_EN_ORDINAL_IRREGULAR = {1: "first", 2: "second", 3: "third", 5: "fifth", 8: "eighth", 9: "ninth",
                         12: "twelfth", 20: "twentieth", 30: "thirtieth"}


def it_number(n: int) -> str:
    """0-99 in Italian: 23 -> 'ventitré', 28 -> 'ventotto'."""
    if n < 20:
        return _IT_UNITS[n]
    tens, unit = divmod(n, 10)
    word = _IT_TENS[tens]
    if unit == 0:
        return word
    if unit in (1, 8):
        word = word[:-1]  # venti + uno -> ventuno
    return word + ("tré" if unit == 3 else _IT_UNITS[unit])


def en_number(n: int) -> str:
    """0-99 in English: 23 -> 'twenty-three'."""
    if n < 20:
        return _EN_UNITS[n]
    tens, unit = divmod(n, 10)
    return _EN_TENS[tens] + (f"-{_EN_UNITS[unit]}" if unit else "")


def _en_ordinal(n: int) -> str:
    if n in _EN_ORDINAL_IRREGULAR:
        return _EN_ORDINAL_IRREGULAR[n]
    if n > 20 and n % 10 in _EN_ORDINAL_IRREGULAR:
        return _EN_TENS[n // 10] + "-" + _EN_ORDINAL_IRREGULAR[n % 10]
    return en_number(n) + "th"


def spoken_number(n: int, language: str) -> str:
    """A small integer as words."""
    n = max(0, min(99, int(n)))
    return en_number(n) if normalize_language(language) == "en" else it_number(n)


def spoken_date(iso_date: str, language: str) -> str:
    """'2026-10-16' -> 'venerdì sedici ottobre' / 'Friday, October sixteenth'. Unparsable -> as is."""
    try:
        day = dt.date.fromisoformat(iso_date)
    except ValueError:
        return iso_date
    if normalize_language(language) == "en":
        return f"{_EN_WEEKDAYS[day.weekday()]}, {_EN_MONTHS[day.month - 1]} {_en_ordinal(day.day)}"
    number = "primo" if day.day == 1 else it_number(day.day)
    return f"{_IT_WEEKDAYS[day.weekday()]} {number} {_IT_MONTHS[day.month - 1]}"


def spoken_time(hhmm: str, language: str) -> str:
    """'20:30' -> 'alle venti e trenta' / 'at eight thirty PM'. Unparsable -> as is."""
    try:
        hour_s, minute_s = hhmm.split(":")[:2]
        hour, minute = int(hour_s), int(minute_s)
    except ValueError:
        return hhmm
    if normalize_language(language) == "en":
        suffix = "PM" if hour >= 12 else "AM"
        hour12 = hour % 12 or 12
        if minute == 0:
            return f"at {en_number(hour12)} o'clock {suffix}"
        return f"at {en_number(hour12)} {'oh ' if minute < 10 else ''}{en_number(minute)} {suffix}"
    lead = "all'una" if hour == 1 else ("a mezzanotte" if hour == 0 and minute == 0 else f"alle {it_number(hour)}")
    return lead if minute == 0 else f"{lead} e {it_number(minute)}"


_LOCATIONS = {
    "it": {"interno": "in sala interna", "terrazza": "in terrazza", "giardino": "in giardino"},
    "en": {"interno": "in the indoor room", "terrazza": "on the terrace", "giardino": "in the garden"},
}


def spoken_location(location: str | None, language: str) -> str:
    """Where the table is, in words ('' when unknown)."""
    if not location:
        return ""
    return _LOCATIONS[normalize_language(language)].get(location.strip().lower(), location)


_AREAS = {
    "it": {"interno": "Sala interna", "terrazza": "Terrazza", "giardino": "Giardino"},
    "en": {"interno": "Indoor room", "terrazza": "Terrace", "giardino": "Garden"},
}


def spoken_area(location: str | None, language: str) -> str:
    """The room as a short label for the on-screen summary ('' when unknown)."""
    if not location:
        return ""
    return _AREAS[normalize_language(language)].get(location.strip().lower(), location)
