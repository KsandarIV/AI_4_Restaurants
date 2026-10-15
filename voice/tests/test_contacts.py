"""Registration dialogue: same behaviour as chat/contatti.py, plus spoken-number handling."""

from __future__ import annotations

import pytest

from voicebot.contacts import (
    RegistrationDialog,
    extract_contacts,
    normalize_spoken_numbers,
    phone_for_speech,
)


@pytest.mark.parametrize(
    ("spoken", "digits"),
    [
        ("tre tre tre uno due tre quattro cinque sei sette", "3331234567"),
        ("three three three one two three four five six seven", "3331234567"),
        ("333, 123, 4567", "3331234567"),
        ("più 39 333 1234567", "+393331234567"),
    ],
)
def test_spoken_numbers_become_digits(spoken: str, digits: str) -> None:
    assert digits in normalize_spoken_numbers(spoken).replace(" ", "")


def test_short_digit_words_are_left_alone() -> None:
    assert normalize_spoken_numbers("siamo in due alle otto") == "siamo in due alle otto"


@pytest.mark.parametrize(
    ("text", "name", "phone"),
    [
        ("Mario Rossi, 333 1234567", "Mario Rossi", "+393331234567"),
        ("Mi chiamo Luca Bianchi, il mio numero è tre tre tre uno due tre quattro cinque sei sette",
         "Luca Bianchi", "+393331234567"),
        ("my name is John Smith, phone 333 123 4567", "John Smith", "+393331234567"),
        ("Sono Anna La Rosa, più 39 333 1234567", "Anna La Rosa", "+393331234567"),
        ("Mario Rossi", "Mario Rossi", None),
        ("333 1234567", None, "+393331234567"),
    ],
)
def test_extract_contacts(text: str, name: str | None, phone: str | None) -> None:
    contacts = extract_contacts(text)
    assert (contacts.name, contacts.phone) == (name, phone)


def test_questions_and_refusals_are_not_names() -> None:
    assert extract_contacts("vorrei prenotare un tavolo").problems == ["other"]
    assert extract_contacts("I would like to book a table").problems == ["other"]
    assert extract_contacts("Non voglio dare i miei dati").problems == ["refusal"]


def test_phone_read_digit_by_digit() -> None:
    assert phone_for_speech("+393331234567") == "3 3 3, 1 2 3, 4 5 6 7"
    assert phone_for_speech("+442071234567", "en").startswith("plus 4 4, ")


def test_full_dialogue_registers_after_confirmation() -> None:
    dialog = RegistrationDialog("it")
    reply, action = dialog.handle("Mario Rossi")
    assert action is None and "telefono" in reply
    reply, action = dialog.handle("tre tre tre uno due tre quattro cinque sei sette")
    assert action is None and "Mario Rossi" in reply and "È corretto" in reply
    reply, action = dialog.handle("sì")
    assert action == "register" and (dialog.name, dialog.phone) == ("Mario Rossi", "+393331234567")


def test_dialogue_all_in_one_utterance_english() -> None:
    dialog = RegistrationDialog("en")
    reply, action = dialog.handle("Mario Rossi, 333 1234567")
    assert action is None and "Is that correct" in reply
    assert dialog.handle("yes")[1] == "register"


def test_correction_after_no_and_restart() -> None:
    dialog = RegistrationDialog("it")
    dialog.handle("Mario Rossi, 333 1234567")
    reply, action = dialog.handle("no, 339 7654321")  # a correction, even after "no"
    assert action is None and "3 3 9, 7 6 5, 4 3 2 1" in reply
    reply, _ = dialog.handle("no")
    assert dialog.name is None and "ricominciamo" in reply
    assert dialog.phase == "collecting"


def test_single_word_does_not_replace_existing_name() -> None:
    dialog = RegistrationDialog("it")
    dialog.handle("Mario Rossi, 333 1234567")
    dialog.handle("mah")
    assert dialog.name == "Mario Rossi"


def test_gives_up_after_three_empty_attempts() -> None:
    dialog = RegistrationDialog("it")
    actions = [dialog.handle("vorrei prenotare")[1] for _ in range(3)]
    assert actions == [None, None, "give_up"]


def test_failed_registration_keeps_data_for_retry() -> None:
    dialog = RegistrationDialog("it")
    dialog.handle("Mario Rossi, 333 1234567")
    assert dialog.handle("sì")[1] == "register"
    dialog.retry_confirmation()
    assert dialog.handle("sì")[1] == "register"
