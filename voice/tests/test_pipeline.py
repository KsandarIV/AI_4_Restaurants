"""End-to-end pipeline test with fake STT/TTS (no models, no network)."""

from __future__ import annotations

import asyncio
import struct
from typing import AsyncIterator

from voicebot.interfaces import ChatMessage
from voicebot.orchestrator import BackendOrchestrator
from voicebot.pipeline.session import VoiceSession
from voicebot.stt import FakeSTT
from voicebot.tts import FakeTTS
from voicebot.vad import EnergyVAD


class _FakeBackend:
    async def stream_chat(self, messages: list[dict[str, str]], timeout_s: float = 30.0) -> AsyncIterator[str]:
        for tok in ["Certo, ", "ho capito. ", "A che ora?"]:
            yield tok

    async def get_menu(self) -> str:
        raise AssertionError("should not be called")

    async def get_info(self) -> str:
        raise AssertionError("should not be called")

    async def check_availability(self, date: str, time: str, party_size: int) -> str:
        raise AssertionError("should not be called")


def _loud_frame(n: int = 320) -> bytes:
    return struct.pack("<%dh" % n, *([3000] * n))


def _silence_frame(n: int = 320) -> bytes:
    return struct.pack("<%dh" % n, *([0] * n))


async def test_full_turn_produces_audio() -> None:
    orch = BackendOrchestrator(backend=_FakeBackend(), system_prompt="sys")  # type: ignore[arg-type]
    session = VoiceSession(
        vad=EnergyVAD(threshold=500.0, silence_ms=60, min_speech_ms=40, sample_rate=16000, frame_ms=20),
        stt=FakeSTT(),
        llm=orch,
        tts=FakeTTS(),
        sample_rate=16000,
    )
    run = asyncio.create_task(session.run())
    for _ in range(15):
        await session.push_audio(_loud_frame())
    for _ in range(6):
        await session.push_audio(_silence_frame())
    out = await asyncio.wait_for(session.audio_out_q.get(), timeout=10.0)
    assert isinstance(out, bytes) and len(out) > 0
    await session.close()
    run.cancel()


async def test_barge_in_drops_stale_audio_and_notifies() -> None:
    events: list[dict[str, str]] = []

    async def cb(payload: dict[str, str]) -> None:
        events.append(payload)

    orch = BackendOrchestrator(backend=_FakeBackend(), system_prompt="sys")  # type: ignore[arg-type]
    session = VoiceSession(
        vad=EnergyVAD(threshold=500.0, silence_ms=200, min_speech_ms=40, sample_rate=16000, frame_ms=20),
        stt=FakeSTT(),
        llm=orch,
        tts=FakeTTS(),
        sample_rate=16000,
        on_control=cb,  # type: ignore[arg-type]
    )
    session.speaking_event.set()
    await session.audio_out_q.put(b"\x01\x02" * 100)
    await session._handle_barge_in()
    assert session.audio_out_q.empty()
    assert events == [{"event": "barge_in"}]
    await session.close()


def test_history_trim() -> None:
    orch = BackendOrchestrator(backend=_FakeBackend(), system_prompt="sys", max_history=4)  # type: ignore[arg-type]
    for i in range(10):
        orch._push(ChatMessage(role="user", content=f"m{i}"))
    assert len(orch.history) <= 5
