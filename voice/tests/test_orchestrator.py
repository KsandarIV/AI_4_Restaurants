"""The voice conversation must behave like the chat bot, end to end against the stub BE."""

from __future__ import annotations

import pytest

from tests.helpers import make_orchestrator, stub_be
from voicebot.orchestrator import BackendOrchestrator, Phase


BOOKING = "Vorrei prenotare un tavolo per due domani alle venti"


async def _register(orch: BackendOrchestrator, request: str = BOOKING) -> str:
    """Ask to book, give name and phone, confirm: returns what the caller hears after the last yes."""
    asked = await orch.reply(request)
    assert orch.phase is Phase.REGISTRATION and "numero di telefono" in asked
    await orch.reply("Mario Rossi, 333 1234567")
    reply = await orch.reply("sì")
    assert orch.phase is Phase.CHAT and orch.registered
    return reply


async def test_call_starts_with_a_short_welcome_and_asks_nothing() -> None:
    async with stub_be() as (url, _):
        orch = make_orchestrator(url)
        opening = await orch.opening()
        assert opening == "Benvenuto alla Trattoria Bella Napoli! Come posso aiutarla?"
        assert orch.phase is Phase.CHAT and "telefono" not in opening
        await orch.aclose()


async def test_menu_and_info_never_ask_for_contact_details() -> None:
    async with stub_be() as (url, state):
        orch = make_orchestrator(url)
        await orch.opening()
        assert "bruschetta" in (await orch.reply("che menu avete?")).lower()
        assert orch.phase is Phase.CHAT and not state.customers
        await orch.aclose()


async def test_booking_request_triggers_registration_and_is_not_asked_twice() -> None:
    async with stub_be() as (url, state):
        orch = make_orchestrator(url)
        await orch.opening()
        asked = await orch.reply(BOOKING)
        assert asked == "Volentieri! Mi dice il suo nome e un numero di telefono?"  # no examples, no surname
        assert state.chat_payloads == []  # nothing reached the LLM before the registration
        await orch.reply("Mario Rossi, 333 1234567")
        done = await orch.reply("sì")
        assert done.startswith("Grazie Mario Rossi, è tutto a posto!") and "Confermi" in done
        assert state.chat_payloads[0]["message"] == BOOKING  # the request is replayed, anonymised
        await orch.aclose()


async def test_streaming_booking_request_is_replayed_after_registration() -> None:
    async with stub_be() as (url, state):
        orch = make_orchestrator(url)
        await orch.reply(BOOKING)
        await orch.reply("Mario Rossi, 333 1234567")
        done = "".join([t async for t in orch.stream_reply("sì")])
        assert "è tutto a posto" in done and "Confermi" in done and len(state.chat_payloads) == 1
        await orch.aclose()


async def test_registration_sends_personal_data_only_to_customers_endpoint() -> None:
    async with stub_be() as (url, state):
        orch = make_orchestrator(url)
        await orch.opening()
        await orch.reply(BOOKING)
        await orch.reply("Mario Rossi, tre tre tre uno due tre quattro cinque sei sette")
        reply = await orch.reply("sì")
        assert "è tutto a posto" in reply and "Mario Rossi" in reply
        assert orch.registered and orch.customer_id.startswith("cust_")
        assert list(state.customers.values()) == [{"name": "Mario Rossi", "phone": "+393331234567"}]
        # the LLM endpoint saw only the booking request, none of the contact data
        assert [p["message"] for p in state.chat_payloads] == [BOOKING]
        await orch.aclose()


async def test_chat_phase_anonymises_and_restores() -> None:
    async with stub_be() as (url, state):
        orch = make_orchestrator(url)
        await _register(orch)
        reply = await orch.reply("Vorrei il menu, scrivetemi a mario.rossi@mail.it")
        sent = state.last_chat_payload
        assert "mario.rossi@mail.it" not in sent["message"] and "[EMAIL_1]" in sent["message"]
        assert sent["customer_id"] == orch.customer_id and sent["client_type"] == "voice"
        assert sent["session_id"].startswith("voice_")
        assert "bruschetta" in reply.lower()
        await orch.aclose()


async def test_booking_requires_yes_and_returns_a_code() -> None:
    async with stub_be() as (url, state):
        orch = make_orchestrator(url)
        await _register(orch)
        assert "Confermi" in await orch.reply("Vorrei prenotare un tavolo per due domani alle venti")
        confirmed = await orch.reply("sì")
        assert "RES-STUB01" in confirmed and "RES-STUB01" in state.reservations
        await orch.aclose()


async def test_streaming_and_sync_modes_agree() -> None:
    async with stub_be() as (url, _):
        orch = make_orchestrator(url)
        await _register(orch)
        sync = await orch.reply("Che orari avete?")
        streamed = "".join([t async for t in orch.stream_reply("Che orari avete?")])
        assert streamed == sync and len([t async for t in orch.stream_reply("menu")]) > 1
        await orch.aclose()


async def test_caller_who_gives_no_details_still_gets_menu_and_is_asked_again_to_book() -> None:
    async with stub_be() as (url, state):
        orch = make_orchestrator(url)
        await orch.reply("vorrei prenotare")
        for _ in range(3):  # three turns without contact details: give up like the chat bot
            reply = await orch.reply("ma quanto costa?")
        assert "Senza questi dati" in reply and orch.phase is Phase.CHAT and not orch.registered
        assert "bruschetta" in (await orch.reply("che menu avete?")).lower()
        assert "nome e un numero di telefono" in await orch.reply("allora vorrei prenotare")  # asked again
        assert orch.phase is Phase.REGISTRATION and not state.customers and state.chat_payloads[-1]["message"] != "vorrei prenotare"
        await orch.aclose()


async def test_failed_registration_can_be_retried_with_a_yes() -> None:
    async with stub_be() as (url, state):
        orch = make_orchestrator(url)
        await orch.reply(BOOKING)
        await orch.reply("Mario Rossi, 333 1234567")
        import voicebot.orchestrator as module

        original = orch._backend.register_customer

        async def broken(name: str, phone: str) -> str:
            raise module.BackendError("down", kind="unreachable")

        orch._backend.register_customer = broken  # type: ignore[method-assign]
        reply = await orch.reply("sì")
        assert "raggiungere il server" in reply and orch.phase is Phase.REGISTRATION
        orch._backend.register_customer = original  # type: ignore[method-assign]
        assert "è tutto a posto" in await orch.reply("sì")
        assert len(state.customers) == 1
        await orch.aclose()


@pytest.mark.parametrize(("status", "fragment"), [(503, "modello linguistico"), (500, "problema")])
async def test_be_errors_become_a_short_spoken_apology(status: int, fragment: str) -> None:
    async with stub_be() as (url, state):
        orch = make_orchestrator(url, require_registration=False)
        state.fail_chat_status = status
        sync = await orch.reply("ciao")
        streamed = "".join([t async for t in orch.stream_reply("ciao")])
        assert fragment in sync and fragment in streamed
        assert "stub failure" not in sync  # never leak technical details to the caller
        await orch.aclose()


async def test_be_unreachable_is_reported_in_plain_words() -> None:
    orch = make_orchestrator("http://127.0.0.1:9", require_registration=False)
    orch._backend._max_retries = 1
    assert "raggiungere il server" in await orch.reply("ciao")
    await orch.aclose()


async def test_registration_can_be_disabled_like_on_the_be() -> None:
    async with stub_be() as (url, _):
        orch = make_orchestrator(url, require_registration=False)
        assert orch.phase is Phase.CHAT and "Come posso aiutarla" in await orch.opening()
        await orch.aclose()


async def test_english_conversation() -> None:
    async with stub_be() as (url, _):
        orch = make_orchestrator(url, language="en")
        assert await orch.opening() == "Welcome to Trattoria Bella Napoli! How can I help you?"
        assert "your name and a phone number" in await orch.reply("I would like to book a table")
        assert "Is that correct" in await orch.reply("My name is John Smith, 333 1234567")
        assert "all set" in await orch.reply("yes")
        await orch.aclose()


async def test_reset_starts_a_new_customer_and_session() -> None:
    async with stub_be() as (url, _):
        orch = make_orchestrator(url)
        await _register(orch)
        old_session = orch.session_id
        orch.reset()
        assert orch.phase is Phase.CHAT and orch.session_id != old_session and not orch.registered
        await orch.aclose()


async def test_history_never_stores_contact_data_and_is_trimmed() -> None:
    async with stub_be() as (url, _):
        orch = make_orchestrator(url)
        await orch.reply(BOOKING)
        await orch.reply("Mario Rossi, 333 1234567")
        assert all("333" not in m.content and "Mario" not in m.content for m in orch.history if m.role == "user")
        for i in range(30):
            orch._remember("user", f"m{i}")
        assert len(orch.history) <= orch._max_history + 1 and orch.history[0].role == "system"
        await orch.aclose()


async def _registered_asking_to_book(url: str) -> BackendOrchestrator:
    orch = make_orchestrator(url)
    await orch.opening()
    await orch.reply("Buongiorno, vorrei prenotare un tavolo")  # lazy registration starts here
    await orch.reply("Mario Rossi, 333 1234567")
    return orch


async def test_a_barge_in_during_the_first_booking_turn_does_not_lose_the_request() -> None:
    """Registered, then the caller talks over the bot while the BE is thinking: the booking request must survive."""
    import asyncio

    async with stub_be() as (url, state):
        orch = await _registered_asking_to_book(url)
        state.chat_delay_s = 3.0  # the BE (cold LLM) takes a while

        async def turn() -> str:
            return "".join([t async for t in orch.stream_reply("sì")])  # confirms the registration, replays the request

        task = asyncio.create_task(turn())
        await asyncio.sleep(0.8)
        task.cancel()  # barge-in: the turn is cancelled before the BE answered
        with __import__("contextlib").suppress(asyncio.CancelledError):
            await task
        assert orch.registered and orch._replay, "the stored booking request was lost"
        state.chat_delay_s = 0.0
        out = "".join([t async for t in orch.stream_reply("domani alle 21 per due persone")])
        assert "Confermi" in out, out  # the request was re-sent together with the new details
        assert orch._replay is None  # ...and forgotten only now that the BE answered
        assert "prenot" in str(state.chat_payloads[-1].get("messages")).lower()
        await orch.aclose()


async def test_a_failed_first_booking_turn_is_retried_not_forgotten() -> None:
    async with stub_be() as (url, state):
        orch = await _registered_asking_to_book(url)
        state.fail_chat_status = 503
        out = await orch.reply("sì")
        assert "modello linguistico" in out and orch._replay  # apology, request kept
        state.fail_chat_status = 0
        assert "Confermi" in await orch.reply("per due persone domani alle 20")
        assert orch._replay is None
        await orch.aclose()
