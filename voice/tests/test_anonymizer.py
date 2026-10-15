"""Anonymiser: same behaviour as chat/anonimizzatore.py + streaming restore + safety net."""

from __future__ import annotations

import pytest

from voicebot.anonymizer import Anonymizer
from voicebot.pii import scrub_pii


def _anon() -> Anonymizer:
    return Anonymizer(use_model=False)  # deterministic: regex layers only


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("scrivimi a mario.rossi@mail.it", "scrivimi a [EMAIL_1]"),
        ("il mio numero è 333 1234567", "il mio numero è [TELEFONO_1]"),
        ("sono Mario Rossi", "sono [NOME_1]"),
        ("a nome di Verdi per due persone", "a nome di [NOME_1] per due persone"),
        ("my name is John Smith", "my name is [NOME_1]"),
        ("RSSMRA80A01H501U", "[CODICE_FISCALE_1]"),
        ("abito in via Garibaldi 12", "abito in [INDIRIZZO_1]"),
    ],
)
def test_personal_data_is_replaced(text: str, expected: str) -> None:
    assert _anon().anonymize(text) == expected


def test_booking_details_are_not_personal_data() -> None:
    text = "vorrei un tavolo per 4 persone domani 16 ottobre alle 20:30"
    assert _anon().anonymize(text) == text


def test_same_value_same_placeholder_and_restore() -> None:
    anon = _anon()
    first = anon.anonymize("sono Mario Rossi e il mio numero è 333 1234567")
    again = anon.anonymize("ripeto: 333 1234567")
    assert first == "sono [NOME_1] e il mio numero è [TELEFONO_1]"
    assert again == "ripeto: [TELEFONO_1]"
    assert anon.restore("Grazie [NOME_1], la richiamiamo al [TELEFONO_1]") == (
        "Grazie Mario Rossi, la richiamiamo al 333 1234567"
    )


def test_placeholder_shape_is_what_the_be_expects() -> None:
    """backend/graph/workflow.py recognises placeholders with r'\\[[A-Z_]+_\\d+\\]'."""
    import re

    out = _anon().anonymize("sono Mario Rossi, mario@x.it, 333 1234567")
    assert all(re.fullmatch(r"\[[A-Z_]+_\d+\]", p) for p in re.findall(r"\[[^\]]+\]", out))


def test_stream_restorer_never_speaks_half_a_placeholder() -> None:
    anon = _anon()
    anon.anonymize("sono Mario Rossi")
    restorer = anon.stream_restorer()
    pieces = [restorer.feed(t) for t in ["Grazie ", "[NOM", "E_1", "], ", "a presto"]]
    pieces.append(restorer.flush())
    assert "".join(pieces) == "Grazie Mario Rossi, a presto"
    assert all("[" not in p for p in pieces)


def test_stream_restorer_releases_text_that_only_looks_like_a_placeholder() -> None:
    restorer = _anon().stream_restorer()
    out = restorer.feed("costa [circa") + restorer.feed(" venti euro per questa portata speciale") + restorer.flush()
    assert out == "costa [circa venti euro per questa portata speciale"


def test_scrub_pii_is_a_stateless_safety_net() -> None:
    cleaned = scrub_pii("chiamami al 333 1234567 o scrivi a a@b.it, siamo in 4 alle 20")
    assert "333" not in cleaned and "a@b.it" not in cleaned
    assert "siamo in 4 alle 20" in cleaned
    assert scrub_pii("[TELEFONO_1] e [NOME_1]") == "[TELEFONO_1] e [NOME_1]"  # idempotent
