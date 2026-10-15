"""Test helpers: synthetic audio, a running stub BE, and ready-made sessions."""

from __future__ import annotations

import asyncio
import struct
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from tests.stub_be import StubState, make_stub
from voicebot.backend import BackendClient
from voicebot.orchestrator import BackendOrchestrator
from voicebot.pipeline.session import VoiceSession
from voicebot.stt import FakeSTT
from voicebot.tts import FakeTTS
from voicebot.vad import EnergyVAD

FRAME = 320  # 20 ms of 16 kHz mono PCM16


def loud(n: int = FRAME) -> bytes:
    """A frame the energy VAD treats as speech."""
    return struct.pack(f"<{n}h", *([3000] * n))


def silence(n: int = FRAME) -> bytes:
    """A silent frame."""
    return struct.pack(f"<{n}h", *([0] * n))


async def say_to(session: VoiceSession, speech_frames: int = 15, silence_frames: int = 6) -> None:
    """Feed one utterance (speech then pause) into the session."""
    for _ in range(speech_frames):
        await session.push_audio(loud())
    for _ in range(silence_frames):
        await session.push_audio(silence())


@asynccontextmanager
async def stub_be() -> AsyncIterator[tuple[str, StubState]]:
    """A real HTTP stub BE on an ephemeral port."""
    server, base_url, state = make_stub()
    try:
        yield base_url, state
    finally:
        server.shutdown()


def make_orchestrator(
    base_url: str, language: str = "it", require_registration: bool = True
) -> BackendOrchestrator:
    """The production orchestrator against a (stub) BE; NER off so tests are deterministic."""
    return BackendOrchestrator(
        backend=BackendClient(base_url=base_url, timeout_s=10.0, chat_timeout_s=10.0),
        language=language,
        require_registration=require_registration,
        use_ner=False,
    )


def make_session(
    llm: BackendOrchestrator,
    script: list[str] | None = None,
    barge_in_min_ms: int = 60,
    on_control: object = None,
    speak_opening: bool = False,
) -> VoiceSession:
    """A session with fast VAD settings, fake STT (scripted) and fake TTS."""
    return VoiceSession(
        vad=EnergyVAD(threshold=500.0, silence_ms=60, min_speech_ms=40, sample_rate=16000, frame_ms=20),
        stt=FakeSTT(script=script),
        llm=llm,
        tts=FakeTTS(),
        sample_rate=16000,
        barge_in_min_ms=barge_in_min_ms,
        on_control=on_control,  # type: ignore[arg-type]
        speak_opening=speak_opening,
    )


async def next_audio(session: VoiceSession, timeout: float = 10.0) -> bytes:
    """The next non-empty audio chunk produced by the session."""
    chunk = await asyncio.wait_for(session.audio_out_q.get(), timeout=timeout)
    assert chunk is not None
    return chunk


async def wait_until(predicate: object, timeout: float = 10.0) -> None:
    """Poll ``predicate()`` until true (async-friendly)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():  # type: ignore[operator]
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not met in time")
