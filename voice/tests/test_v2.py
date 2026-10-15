"""V2 on-demand: STT -> BE /api/chat -> TTS, senza mic né rete (stub BE + fake)."""

from __future__ import annotations

import struct

import pytest

from tests.stub_be import make_stub
from voicebot.backend import BackendClient
from voicebot.stt import FakeSTT
from voicebot.tts import FakeTTS
from voicebot.v2 import answer_once


def _loud(n: int = 3200) -> bytes:
    return struct.pack("<%dh" % n, *([3000] * n))


@pytest.fixture()
async def wired() -> tuple[BackendClient, FakeSTT, FakeTTS, str, str]:
    server, base_url, _ = make_stub()
    backend = BackendClient(base_url=str(base_url), timeout_s=10.0)
    try:
        yield backend, FakeSTT(), FakeTTS(), "sess_test", "anon_test"
    finally:
        await backend.aclose()
        server.shutdown()


async def test_v2_turn_end_to_end(wired: object) -> None:
    backend, stt, tts, sess, cust = wired  # type: ignore[misc]
    user_text, reply, audio = await answer_once(_loud(), 16000, stt, backend, tts, sess, cust)
    assert user_text == stt.fixed_text  # type: ignore[union-attr]
    assert "RES-STUB01" in reply  # il testo fake contiene "prenot" -> conferma stub
    assert len(audio) > 0


async def test_v2_silence_gives_retry_message(wired: object) -> None:
    backend, stt, tts, sess, cust = wired  # type: ignore[misc]
    user_text, reply, audio = await answer_once(b"\x00\x00" * 3200, 16000, stt, backend, tts, sess, cust)
    assert user_text == "" and "ripetere" in reply and audio == b""


async def test_backend_chat_sync_shape(wired: object) -> None:
    backend = wired[0]  # type: ignore[index]
    resp = await backend.chat("vorrei prenotare", "s1", "c1")  # type: ignore[union-attr]
    assert "RES-STUB01" in resp["reply"] and resp["session_id"] == "s1"
