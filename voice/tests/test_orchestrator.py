"""The voice conversation must behave like the chat bot, end to end against the stub BE."""

from __future__ import annotations

import pytest

from tests.helpers import make_orchestrator, stub_be
from voicebot.orchestrator import BackendOrchestrator, Phase


async def _register(orch: BackendOrchestrator) -> None:
    await orch.reply("Mario Rossi, 333 1234567")
    assert orch.phase is Phase.REGISTRATION
    assert "registrati" in (await orch.reply("sì")).lower() or orch.phase is Phase.CHAT
    assert orch.phase is Phase.CHAT


async def test_call_starts_by_asking_for_contact_details() -> None:
    async with stub_be() as (url, _):
        orch = make_orchestrator(url)
        opening = await orch.opening()
        assert "nome e cognome" in opening and "telefono" in opening
        assert orch.phase is Phase.REGISTRATION
        await orch.aclose()


async def test_registration_sends_personal_data_only_to_customers_endpoint() -> None:
    async with stub_be() as (url, state):
        orch = make_orchestrator(url)
        await orch.opening()
        await orch.reply("Mario Rossi, tre tre tre uno due tre quattro cinque sei sette")
        reply = await orch.reply("sì")
        assert "Registrazione completata" in reply and "Mario Rossi" in reply
        assert orch.registered and orch.customer_id.startswith("cust_")
        assert list(state.customers.values()) == [{"name": "Mario Rossi", "phone": "+393331234567"}]
        assert state.chat_payloads == []  # the LLM endpoint saw nothing of the registration phase
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


async def test_unregistered_caller_cannot_book_but_can_ask_for_the_menu() -> None:
    async with stub_be() as (url, _):
        orch = make_orchestrator(url)
        for _ in range(3):  # three turns without contact details: give up like the chat bot
            reply = await orch.reply("vorrei prenotare")
        assert "Senza questi dati" in reply and orch.phase is Phase.CHAT and not orch.registered
        assert "registrazione" in await orch.reply("Vorrei prenotare un tavolo")
        assert "bruschetta" in (await orch.reply("che menu avete?")).lower()
        await orch.aclose()


async def test_failed_registration_can_be_retried_with_a_yes() -> None:
    async with stub_be() as (url, state):
        orch = make_orchestrator(url)
        await orch.reply("Mario Rossi, 333 1234567")
        import voicebot.orchestrator as module

        original = orch._backend.register_customer

        async def broken(name: str, phone: str) -> str:
            raise module.BackendError("down", kind="unreachable")

        orch._backend.register_customer = broken  # type: ignore[method-assign]
        reply = await orch.reply("sì")
        assert "raggiungere il server" in reply and orch.phase is Phase.REGISTRATION
        orch._backend.register_customer = original  # type: ignore[method-assign]
        assert "Registrazione completata" in await orch.reply("sì")
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
        assert "first and last name" in await orch.opening()
        assert "Is that correct" in await orch.reply("My name is John Smith, 333 1234567")
        assert "Registration complete" in await orch.reply("yes")
        await orch.aclose()


async def test_reset_starts_a_new_customer_and_session() -> None:
    async with stub_be() as (url, _):
        orch = make_orchestrator(url)
        await _register(orch)
        old_session = orch.session_id
        orch.reset()
        assert orch.phase is Phase.REGISTRATION and orch.session_id != old_session and not orch.registered
        await orch.aclose()


async def test_history_never_stores_contact_data_and_is_trimmed() -> None:
    async with stub_be() as (url, _):
        orch = make_orchestrator(url)
        await orch.reply("Mario Rossi, 333 1234567")
        assert all("333" not in m.content and "Mario" not in m.content for m in orch.history if m.role == "user")
        for i in range(30):
            orch._remember("user", f"m{i}")
        assert len(orch.history) <= orch._max_history + 1 and orch.history[0].role == "system"
        await orch.aclose()
