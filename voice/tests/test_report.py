"""The spoken final report after a booking: built from the BE's data, ends with a last "yes"."""

from __future__ import annotations

import asyncio

import pytest

from tests.helpers import make_orchestrator, make_session, say_to, stub_be, wait_until
from voicebot.orchestrator import BackendOrchestrator
from voicebot.spoken import it_number, spoken_date, spoken_location, spoken_time


@pytest.mark.parametrize(("n", "words"), [(0, "zero"), (21, "ventuno"), (23, "ventitré"), (28, "ventotto"),
                                          (30, "trenta"), (59, "cinquantanove")])
def test_italian_numbers(n: int, words: str) -> None:
    assert it_number(n) == words


@pytest.mark.parametrize(
    ("hhmm", "lang", "expected"),
    [("20:30", "it", "alle venti e trenta"), ("13:00", "it", "alle tredici"), ("01:15", "it", "all'una e quindici"),
     ("20:30", "en", "at eight thirty PM"), ("12:00", "en", "at twelve o'clock PM"), ("09:05", "en", "at nine oh five AM"),
     ("boh", "it", "boh")],
)
def test_spoken_time(hhmm: str, lang: str, expected: str) -> None:
    assert spoken_time(hhmm, lang) == expected


def test_spoken_date_and_location() -> None:
    assert spoken_date("2026-10-16", "it") == "venerdì sedici ottobre"
    assert spoken_date("2026-11-01", "it") == "domenica primo novembre"
    assert spoken_date("2026-10-16", "en") == "Friday, October sixteenth"
    assert spoken_date("2026-10-23", "en") == "Friday, October twenty-third"
    assert spoken_date("garbage", "it") == "garbage"
    assert spoken_location("terrazza", "it") == "in terrazza" and spoken_location(None, "it") == ""


async def _registered(url: str, language: str = "it") -> BackendOrchestrator:
    orch = make_orchestrator(url, language=language)
    await orch.reply("Vorrei prenotare" if language == "it" else "I would like to book")  # triggers registration
    await orch.reply("Mario Rossi, 333 1234567")
    await orch.reply("sì" if language == "it" else "yes")
    assert orch.registered
    return orch


async def test_booking_is_followed_by_a_spoken_report_and_a_last_yes() -> None:
    async with stub_be() as (url, state):
        orch = await _registered(url)
        events: list[dict[str, str]] = []

        async def hook(payload: dict[str, str]) -> None:
            events.append(payload)

        orch.on_event = hook
        await orch.reply("Vorrei prenotare un tavolo per quattro persone domani alle 21")
        reply = await orch.reply("sì")
        assert "Il codice è RES-STUB01" in reply  # the BE's own answer comes first
        assert "Riepilogo finale per Mario Rossi" in reply and "per quattro persone" in reply
        assert "alle ventuno" in reply and "in terrazza" in reply and "tavolo undici" in reply
        assert reply.rstrip().endswith("È tutto corretto?")
        reservation = next(e for e in events if e["event"] == "reservation")
        assert (reservation["code"], reservation["guests"], reservation["time"], reservation["status"]) == (
            "RES-STUB01", "4", "21:00", "CONFIRMED")
        assert reservation["customer_id"] == orch.customer_id
        final = await orch.reply("sì, tutto corretto")
        assert final.startswith("Perfetto per Mario Rossi, grazie!") and orch._awaiting_final is None
        assert len(state.chat_payloads) == 3  # replayed request + booking; the last "yes" never went to the LLM
        await orch.aclose()


async def test_the_report_is_also_spoken_in_streaming_mode() -> None:
    async with stub_be() as (url, _):
        orch = await _registered(url)
        await orch.reply("Vorrei prenotare un tavolo per due")
        streamed = "".join([t async for t in orch.stream_reply("sì")])
        assert "RES-STUB01" in streamed and "Riepilogo finale" in streamed and "È tutto corretto?" in streamed
        await orch.aclose()


async def test_the_report_is_in_english_when_the_call_is_in_english() -> None:
    async with stub_be() as (url, _):
        orch = await _registered(url, "en")
        await orch.reply("I would like to book a table for two people tomorrow at 20:30")
        reply = await orch.reply("yes")
        assert "Final summary for Mario Rossi" in reply and "for two people" in reply
        assert "at eight thirty PM" in reply and "Is everything correct?" in reply
        assert (await orch.reply("yes, perfect")).startswith("Perfect for Mario Rossi")
        await orch.aclose()


async def test_a_no_asks_what_to_change_and_a_qualified_yes_goes_to_the_agent() -> None:
    async with stub_be() as (url, state):
        orch = await _registered(url)
        await orch.reply("Vorrei prenotare un tavolo per due")
        await orch.reply("sì")
        assert "cosa vuole cambiare" in await orch.reply("no")
        await orch.reply("Vorrei prenotare un altro tavolo")  # fresh booking -> report again later
        await orch.reply("sì")
        before = len(state.chat_payloads)
        reply = await orch.reply("sì ma spostalo alle 22")  # "yes, but..." is NOT the last confirmation
        assert len(state.chat_payloads) == before + 1 and "Perfetto" not in reply
        await orch.aclose()


async def test_cancel_and_modify_are_reported_too() -> None:
    async with stub_be() as (url, _):
        orch = await _registered(url)
        await orch.reply("Vorrei prenotare un tavolo per due alle 20")
        await orch.reply("sì")
        changed = await orch.reply("Modifica la prenotazione RES-STUB01 alle 21 per 3 persone")
        assert "Prenotazione aggiornata per Mario Rossi" in changed and "per tre persone" in changed
        assert "alle ventuno" in changed and "Il codice resta RES-STUB01" in changed
        cancelled = await orch.reply("Cancella la prenotazione RES-STUB01")
        assert "RES-STUB01 per Mario Rossi risulta cancellata" in cancelled
        assert orch._awaiting_final is None  # nothing left to confirm after a cancellation
        await orch.aclose()


async def test_no_second_report_when_nothing_changed() -> None:
    async with stub_be() as (url, _):
        orch = await _registered(url)
        await orch.reply("Vorrei prenotare un tavolo per due")
        first = await orch.reply("sì")
        assert "Riepilogo finale" in first
        again = await orch.reply("Mi ripeti il codice RES-STUB01?")  # the stub echoes it back
        assert "Riepilogo finale" not in again and "Prenotazione aggiornata" not in again
        await orch.aclose()


async def test_no_report_for_anonymous_callers_or_unknown_codes() -> None:
    async with stub_be() as (url, _):
        anonymous = make_orchestrator(url, require_registration=False)
        assert await anonymous._final_report("La prenotazione RES-STUB01 è confermata") == ""
        await anonymous.aclose()
        orch = await _registered(url)
        assert await orch._final_report("Il codice è RES-NOPE99") == ""  # 404 -> silence, not a wrong report
        assert await orch._final_report("nessun codice qui") == ""
        await orch.aclose()


async def test_the_session_forwards_reservation_events_to_the_client() -> None:
    async with stub_be() as (url, _):
        events: list[dict[str, str]] = []

        async def on_control(payload: dict[str, str]) -> None:
            events.append(payload)

        llm = make_orchestrator(url)
        script = ["Vorrei prenotare un tavolo per due", "Mario Rossi, 333 1234567", "sì", "sì"]
        session = make_session(llm, script=script, on_control=on_control)
        run = asyncio.create_task(session.run())
        for k in range(len(script)):
            await say_to(session)
            await wait_until(lambda k=k: sum(e["event"] == "reply" for e in events) >= k + 1)
        kinds = [e["event"] for e in events]
        assert "registered" in kinds and "reservation" in kinds
        assert kinds.index("registered") < kinds.index("reservation")
        spoken = " ".join(session.tts.spoken)  # type: ignore[attr-defined]
        assert "Riepilogo finale" in spoken and "R E S, S T U B 0 1" in spoken
        await session.close()
        await run


async def test_whisper_style_time_is_understood_by_the_stub() -> None:
    """Whisper writes "alle 20 e 30": the report must say 20:30, not 20:00 (found in the real-model run)."""
    async with stub_be() as (url, _):
        orch = await _registered(url)
        await orch.reply("Vorrei prenotare un tavolo per due persone domani alle 20 e 30")
        assert "alle venti e trenta" in await orch.reply("sì")
        await orch.aclose()


async def test_popup_events_carry_name_and_room_only_when_asked_and_close_on_the_final_yes() -> None:
    async with stub_be() as (url, _):
        orch = await _registered(url)
        events: list[dict[str, str]] = []

        async def hook(payload: dict[str, str]) -> None:
            events.append(payload)

        orch.on_event = hook
        await orch.reply("Vorrei prenotare un tavolo per due domani alle venti")
        await orch.reply("sì")
        booked = next(e for e in events if e["event"] == "reservation")
        assert booked["name"] == "Mario Rossi" and booked["status"] == "CONFIRMED"
        assert booked["area"] == ""  # the caller never named a room: the pop-up shows none
        assert not any(e["event"] == "reservation_confirmed" for e in events)  # still waiting for the final yes
        await orch.reply("sì, tutto corretto")
        assert [e["event"] for e in events].count("reservation_confirmed") == 1
        await orch.aclose()


async def test_popup_shows_the_room_the_caller_asked_for() -> None:
    async with stub_be() as (url, _):
        orch = await _registered(url)
        events: list[dict[str, str]] = []

        async def hook(payload: dict[str, str]) -> None:
            events.append(payload)

        orch.on_event = hook
        await orch.reply("Vorrei prenotare in terrazza un tavolo per due domani alle venti")
        await orch.reply("sì")
        booked = next(e for e in events if e["event"] == "reservation")
        assert booked["area"] == "Terrazza"
        await orch.aclose()
