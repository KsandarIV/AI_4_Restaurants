"""All unregistered callers share one anonymous id (the BE's prompt cache stays warm); registered ones get their own."""

from __future__ import annotations

from tests.helpers import make_orchestrator, stub_be
from voicebot.orchestrator import ANON_CUSTOMER_ID


async def test_unregistered_callers_share_the_anonymous_id_and_registration_replaces_it() -> None:
    async with stub_be() as (url, state):
        one, two = make_orchestrator(url), make_orchestrator(url)
        assert one.customer_id == two.customer_id == ANON_CUSTOMER_ID and not one.registered
        await one.reply("che menu avete?")
        assert state.chat_payloads[-1]["customer_id"] == ANON_CUSTOMER_ID
        await one.reply("Vorrei prenotare un tavolo")
        await one.reply("Mario Rossi, 333 1234567")
        await one.reply("sì")
        assert one.registered and one.customer_id != ANON_CUSTOMER_ID and two.customer_id == ANON_CUSTOMER_ID
        await one.aclose()
        await two.aclose()
