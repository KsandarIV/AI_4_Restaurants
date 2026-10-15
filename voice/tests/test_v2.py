"""v2 on-demand mode: STT -> chat conversation -> TTS, plus the optional CHAT-service transport."""

from __future__ import annotations

import argparse
import json

import httpx
import pytest

from tests.helpers import loud, make_orchestrator, silence, stub_be
from voicebot.chat_service import ChatServiceOrchestrator
from voicebot.config import Settings
from voicebot.orchestrator import BackendOrchestrator
from voicebot.stt import FakeSTT
from voicebot.tts import FakeTTS
from voicebot.v2 import amain, answer_once, build_conversation, hear_and_reply


async def test_v2_runs_the_whole_chat_conversation_by_voice() -> None:
    async with stub_be() as (url, state):
        conversation = make_orchestrator(url)
        stt, tts = FakeSTT(script=["Vorrei prenotare un tavolo per due", "Mario Rossi, 333 1234567", "sì", "sì"]), FakeTTS()
        replies = []
        for _ in range(4):
            heard, reply, audio = await answer_once(loud(3200), 16000, stt, conversation, tts)
            assert heard and reply and len(audio) > 0
            replies.append(reply)
        assert "numero di telefono" in replies[0] and "È corretto" in replies[1]
        assert "è tutto a posto" in replies[2] and "Confermi" in replies[2] and "RES-STUB01" in replies[3]
        assert state.customers and not any("333" in str(p.get("message")) for p in state.chat_payloads)
        assert all(p["client_type"] == "voice" for p in state.chat_payloads)
        await conversation.aclose()


async def test_v2_uses_the_synchronous_endpoint_not_the_stream() -> None:
    """The point of v2: one complete reply from POST /api/chat, nothing streamed."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/api/customers":
            return httpx.Response(200, json={"customer_id": "cust_1"})
        return httpx.Response(200, json={"reply": "Certo."})

    from voicebot.backend import BackendClient

    backend = BackendClient("http://be.test", transport=httpx.MockTransport(handler))
    conversation = BackendOrchestrator(backend, require_registration=False, use_ner=False)
    assert await conversation.reply("ciao") == "Certo."
    assert calls == ["/api/chat"]
    await conversation.aclose()


async def test_silence_asks_to_repeat_without_calling_the_be() -> None:
    async with stub_be() as (url, state):
        conversation = make_orchestrator(url, require_registration=False)
        heard, reply = await hear_and_reply(silence(3200), 16000, FakeSTT(), conversation)
        assert heard == "" and "ripetere" in reply and state.chat_payloads == []
        _, reply_en = await hear_and_reply(silence(3200), 16000, FakeSTT(), conversation, language="en")
        assert "repeat" in reply_en
        await conversation.aclose()


# ---------------- the chat service transport ----------------


def _chat_service() -> tuple[httpx.MockTransport, list[tuple[str, dict[str, object]]]]:
    seen: list[tuple[str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        seen.append((request.url.path, body))
        if request.url.path == "/chat/session":
            return httpx.Response(200, json={"session_id": "chat_1", "phase": "registration",
                                             "reply": "Benvenuto! Mi servono nome e telefono."})
        if body.get("session_id") != "chat_1":
            return httpx.Response(404, json={"detail": "expired"})
        return httpx.Response(200, json={"reply": f"eco: {body['text']}", "phase": "chat"})

    return httpx.MockTransport(handler), seen


async def test_chat_service_transport_is_a_pure_speech_wrapper() -> None:
    transport, seen = _chat_service()
    conversation = ChatServiceOrchestrator("http://chat.test:8002", transport=transport)
    assert "nome e telefono" in await conversation.opening()
    assert await conversation.reply("Mario Rossi") == "eco: Mario Rossi"
    assert "".join([t async for t in conversation.stream_reply("ciao")]) == "eco: ciao"
    assert [path for path, _ in seen] == ["/chat/session", "/chat/message", "/chat/message"]
    assert conversation.phase == "chat"
    await conversation.aclose()


async def test_chat_service_recovers_when_its_session_expired() -> None:
    transport, _ = _chat_service()
    conversation = ChatServiceOrchestrator("http://chat.test:8002", transport=transport)
    await conversation.opening()
    conversation.session_id = "chat_stale"
    assert "problema" in await conversation.reply("ciao")  # spoken apology, no crash
    assert await conversation.reply("ciao") == "eco: ciao"  # opened a fresh session by itself
    await conversation.aclose()


async def test_chat_service_down_is_reported_in_plain_words() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    conversation = ChatServiceOrchestrator("http://chat.test:8002", transport=httpx.MockTransport(handler))
    assert "raggiungere il server" in await conversation.opening()
    await conversation.aclose()


def test_build_conversation_picks_the_transport() -> None:
    assert isinstance(build_conversation(Settings()), BackendOrchestrator)
    assert isinstance(build_conversation(Settings(chat_service_url="http://chat:8002")), ChatServiceOrchestrator)


async def test_text_mode_session_end_to_end(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """`python -m voicebot.v2 --text` against the stub BE, typing instead of speaking."""
    async with stub_be() as (url, state):
        monkeypatch.setenv("BACKEND_BASE_URL", url)
        monkeypatch.setenv("STT_BACKEND", "fake")
        typed = iter(["Vorrei prenotare un tavolo", "Mario Rossi, 333 1234567", "sì", "che menu avete?", "q"])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(typed))
        code = await amain(argparse.Namespace(text=True, no_speaker=True, verbose=False))
        out = capsys.readouterr().out
        assert code == 0
        assert "Come posso aiutarla" in out and "è tutto a posto" in out and "bruschetta" in out.lower()
        assert len(state.customers) == 1
