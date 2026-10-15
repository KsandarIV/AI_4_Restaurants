"""The LLM's context lives in the BE session: the voice bot refreshes it every N exchanges and finally ends the call."""

from __future__ import annotations

import asyncio

from tests.helpers import make_orchestrator, make_session, say_to, stub_be, wait_until
from voicebot.orchestrator import ANON_CUSTOMER_ID
from voicebot.orchestrator import BackendOrchestrator

BOOKING = "Vorrei prenotare un tavolo"


async def _registered(url: str, **kwargs: int) -> BackendOrchestrator:
    orch = make_orchestrator(url, **kwargs)
    await orch.reply(BOOKING)
    await orch.reply("Mario Rossi, 333 1234567")
    await orch.reply("sì")
    assert orch.registered
    return orch


async def _fill(orch: BackendOrchestrator, n: int) -> None:
    for _ in range(n):
        await orch.reply("che menu avete?")


async def test_a_full_context_is_refreshed_with_a_recap_and_the_customer_stays_registered() -> None:
    async with stub_be() as (url, state):
        orch = await _registered(url, max_exchanges=4, max_resets=3)
        customer, session = orch.customer_id, orch.session_id
        await _fill(orch, 3)  # 1 (the replayed request) + 3 = 4 exchanges
        sent = len(state.chat_payloads)
        recap = await orch.reply("e gli orari?")
        assert "sto gestendo molte richieste" in recap and "Mario" in recap and "una prenotazione o una modifica" in recap
        assert len(state.chat_payloads) == sent  # that utterance never reached the BE
        assert orch.session_id != session and orch.customer_id == customer and orch.registered
        assert orch._exchanges == 0 and orch.history[0].role == "system" and len(orch.history) == 2
        assert "bruschetta" in (await orch.reply("che menu avete?")).lower()  # the new session works at once
        assert state.chat_payloads[-1]["session_id"] == orch.session_id != session
        await orch.aclose()


async def test_third_refresh_warns_and_the_fourth_ends_the_call() -> None:
    async with stub_be() as (url, _):
        orch = await _registered(url, max_exchanges=4, max_resets=3)
        replies = []
        for _ in range(4):
            await _fill(orch, 4 - orch._exchanges)
            replies.append(await orch.reply("ancora una domanda"))
        assert all("sto gestendo molte richieste" in r for r in replies[:3])
        assert "ricominciare tutto da capo" not in replies[0] + replies[1] and "ricominciare tutto da capo" in replies[2]
        assert "limite di questa conversazione" in replies[3] and orch.ended
        assert await orch.reply("hallo?") == ""  # nothing more is processed
        orch.reset()
        assert not orch.ended and orch._resets == 0  # a new conversation starts clean
        await orch.aclose()


async def test_reaching_a_booking_resets_the_counters_and_the_final_yes_starts_a_fresh_session() -> None:
    async with stub_be() as (url, _):
        orch = await _registered(url, max_exchanges=6, max_resets=1)
        orch._resets = 1  # one refresh already used
        await orch.reply("Vorrei prenotare un tavolo per due domani alle venti")
        await orch.reply("sì")  # booked: the BE answers, the spoken report follows
        assert orch._resets == 0 and orch._awaiting_final is not None
        session = orch.session_id
        await orch.reply("sì, tutto corretto")  # the final yes: goal reached
        assert orch.session_id != session and orch._exchanges == 0
        await orch.aclose()


async def test_the_session_tells_the_client_when_the_call_is_over() -> None:
    async with stub_be() as (url, _):
        events: list[str] = []

        async def on_control(payload: dict[str, str]) -> None:
            events.append(payload["event"])

        orch = make_orchestrator(url, require_registration=False, max_exchanges=1, max_resets=0)
        session = make_session(orch, script=["che menu avete?", "e gli orari?"], on_control=on_control)
        run = asyncio.create_task(session.run())
        for _ in range(2):
            await say_to(session)
        await wait_until(lambda: "call_ended" in events, timeout=10)
        assert events.count("call_ended") == 1 and orch.ended
        await session.close()
        await run


async def test_warm_up_sends_one_throwaway_turn_and_never_fails() -> None:
    from voicebot.config import Settings
    from voicebot.pipeline.server import warm_backend

    async with stub_be() as (url, state):
        await warm_backend(Settings(backend_base_url=url))
        assert [p["session_id"] for p in state.chat_payloads] == ["voice_warmup"]
        assert state.chat_payloads[0]["customer_id"] == ANON_CUSTOMER_ID and not state.customers
    await warm_backend(Settings(backend_base_url="http://127.0.0.1:9", backend_timeout_s=1.0))  # BE down: silent
