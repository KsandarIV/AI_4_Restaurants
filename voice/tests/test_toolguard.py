"""A caller must never hear the LLM talk about its tools or ask a pointless permission."""

from __future__ import annotations

import pytest

from tests.helpers import make_orchestrator, stub_be
from voicebot.toolguard import leaks_tool_talk


@pytest.mark.parametrize("text", [
    "Per vedere il menu vegetariano, devo prima chiamare get_menu. Vuole che verifichi i piatti disponibili oggi?",
    "Chiamo get_restaurant_info con key='address'.",
    "Vuole che controlli la disponibilità?",
    "Uso lo strumento per cercare.",
    "I need to call check_availability first.",
    "Certamente. Posso mostrarle i piatti vegetariani del nostro menu.",
    "Posso fornirle l'indirizzo della Trattoria Bella Napoli.",
    "Posso mostrarti i piatti vegetariani del nostro menu.",
    "Posso fornirti le informazioni generali sulla Trattoria Bella Napoli.",
])
def test_tool_talk_is_detected(text: str) -> None:
    assert leaks_tool_talk(text)


@pytest.mark.parametrize("text", [
    "Abbiamo bruschetta, mozzarella di bufala e spaghetti alle vongole.",
    "Il codice è RES-STUB01. Vuole che prenoti per le venti?",
    "Grazie [NOME_1], la aspettiamo venerdì sedici ottobre.",
    "Siamo aperti dalle dodici e trenta alle quattordici e trenta.",
    "L'indirizzo è Via Toledo centoquarantadue. Posso fornirle altro?",
])
def test_normal_replies_pass(text: str) -> None:
    assert not leaks_tool_talk(text)


async def test_a_reply_about_tools_is_retried_once_then_replaced() -> None:
    async with stub_be() as (url, state):
        orch = make_orchestrator(url, require_registration=False)
        state.canned_replies = ["Devo prima chiamare get_menu. Vuole che verifichi?"] * 2
        reply = await orch.reply("che menu avete?")
        assert "non sono riuscito a recuperare" in reply and "get_menu" not in reply
        assert len(state.chat_payloads) == 2 and "senza nominarli" in state.chat_payloads[1]["message"]
        state.canned_replies = ["Chiamo get_menu."] * 2
        streamed = "".join([t async for t in orch.stream_reply("che menu avete?")])
        assert "non sono riuscito a recuperare" in streamed and "get_menu" not in streamed
        await orch.aclose()


async def test_the_retry_gets_the_real_answer() -> None:
    async with stub_be() as (url, state):
        orch = make_orchestrator(url, require_registration=False)
        state.canned_replies = ["Devo prima chiamare get_menu.", "Abbiamo bruschetta e sorbetto al limone."]
        assert "bruschetta" in await orch.reply("che menu avete?")
        state.canned_replies = ["Chiamo get_menu per lei.", "Abbiamo spaghetti alle vongole e babà."]
        streamed = "".join([t async for t in orch.stream_reply("che menu avete?")])
        assert streamed == "Abbiamo spaghetti alle vongole e babà." and "get_menu" not in streamed
        await orch.aclose()


async def test_a_short_opening_word_does_not_hide_a_non_answer_in_the_next_sentence() -> None:
    async with stub_be() as (url, state):
        orch = make_orchestrator(url, require_registration=False)
        state.canned_replies = ["Certamente. Posso mostrarle i piatti vegetariani del nostro menu.", "Abbiamo la parmigiana di melanzane."]
        streamed = "".join([t async for t in orch.stream_reply("avete piatti vegetariani?")])
        assert streamed == "Abbiamo la parmigiana di melanzane."
        await orch.aclose()
