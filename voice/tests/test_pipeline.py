"""The real-time core loop: turns, events, barge-in, shutdown (fake STT/TTS, stub BE)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from tests.helpers import loud, make_orchestrator, make_session, next_audio, say_to, silence, stub_be, wait_until
from voicebot.interfaces import AbstractLLMOrchestrator, AbstractSTT
from voicebot.pipeline.session import VoiceSession
from voicebot.stt import FakeSTT
from voicebot.tts import FakeTTS
from voicebot.vad import EnergyVAD


class ScriptedLLM(AbstractLLMOrchestrator):
    """Orchestrator with controllable latency: no network involved."""

    def __init__(self, reply: str = "Certo, ho capito. A che ora?", delay_s: float = 0.0) -> None:
        self.history = []
        self.reply_text, self.delay_s = reply, delay_s
        self.asked: list[str] = []
        self.cancelled = 0
        self.resets = 0

    async def opening(self) -> str:
        return "Benvenuto!"

    async def stream_reply(self, user_text: str) -> AsyncIterator[str]:
        self.asked.append(user_text)
        try:
            await asyncio.sleep(self.delay_s)
            for word in self.reply_text.split(" "):
                yield word + " "
        except asyncio.CancelledError:
            self.cancelled += 1
            raise

    def reset(self) -> None:
        self.resets += 1


def _session(llm: AbstractLLMOrchestrator, stt: AbstractSTT | None = None, **kwargs: object) -> VoiceSession:
    return VoiceSession(
        vad=EnergyVAD(threshold=500.0, silence_ms=60, min_speech_ms=40, sample_rate=16000, frame_ms=20),
        stt=stt or FakeSTT(fixed_text="ciao"),
        llm=llm,
        tts=FakeTTS(),
        sample_rate=16000,
        barge_in_min_ms=int(kwargs.pop("barge_in_min_ms", 60)),  # type: ignore[call-overload]
        **kwargs,  # type: ignore[arg-type]
    )


async def test_full_turn_produces_audio_and_events_in_order() -> None:
    events: list[str] = []

    async def on_control(payload: dict[str, str]) -> None:
        events.append(payload["event"])

    llm = ScriptedLLM()
    session = _session(llm, on_control=on_control, speak_opening=False)
    run = asyncio.create_task(session.run())
    await say_to(session)
    assert len(await next_audio(session)) > 0
    await wait_until(lambda: "reply" in events)
    assert events[:4] == ["heard", "transcript", "thinking", "reply"]
    assert llm.asked == ["ciao"]
    await session.close()
    await run


async def test_bot_speaks_first_like_the_chat_bot() -> None:
    llm = ScriptedLLM()
    session = _session(llm, speak_opening=True)
    run = asyncio.create_task(session.run())
    assert len(await next_audio(session)) > 0  # greeting, before the caller said anything
    assert session.tts.spoken == ["Benvenuto!"]  # type: ignore[attr-defined]
    await session.close()
    await run


async def test_full_registration_and_booking_by_voice_against_the_be() -> None:
    async with stub_be() as (url, state):
        events: list[dict[str, str]] = []

        async def on_control(payload: dict[str, str]) -> None:
            events.append(payload)

        llm = make_orchestrator(url)
        script = ["Vorrei prenotare un tavolo per due", "Mario Rossi, 333 1234567", "sì", "sì"]
        session = make_session(llm, script=script, on_control=on_control, speak_opening=True)
        run = asyncio.create_task(session.run())

        def replies() -> int:
            return sum(e["event"] == "reply" for e in events)

        await wait_until(lambda: replies() >= 1)  # the greeting
        for k in range(len(script)):  # one utterance, one reply
            await say_to(session)
            await wait_until(lambda k=k: replies() >= k + 2)
        assert any("RES-STUB01" in e.get("text", "") for e in events)
        assert len(state.customers) == 1 and "RES-STUB01" in state.reservations
        spoken = " ".join(session.tts.spoken)  # type: ignore[attr-defined]
        assert "R E S, S T U B 0 1" in spoken  # booking code is spelled out for the caller
        sent = " ".join(str(p.get("message", "")) for p in state.chat_payloads)
        assert "333" not in sent and "Mario" not in sent  # personal data never reached the LLM endpoint
        await session.close()
        await run


async def test_barge_in_while_thinking_cancels_the_turn_and_answers_the_new_question() -> None:
    events: list[str] = []

    async def on_control(payload: dict[str, str]) -> None:
        events.append(payload["event"])

    llm = ScriptedLLM(delay_s=5.0)  # slow LLM: the caller talks again while it "thinks"
    session = _session(llm, on_control=on_control, speak_opening=False)
    run = asyncio.create_task(session.run())
    await say_to(session)
    await wait_until(lambda: llm.asked == ["ciao"])
    assert session.is_speaking
    llm.delay_s = 0.0
    for _ in range(10):  # more speech, longer than barge_in_min_ms
        await session.push_audio(loud())
    for _ in range(6):
        await session.push_audio(silence())
    await wait_until(lambda: "barge_in" in events)
    assert llm.cancelled == 1  # the slow turn really was cancelled, not just ignored
    assert len(await next_audio(session)) > 0  # and the second utterance got its answer
    assert llm.asked == ["ciao", "ciao"]
    await session.close()
    await run


async def test_short_noise_while_speaking_is_not_a_barge_in() -> None:
    events: list[str] = []

    async def on_control(payload: dict[str, str]) -> None:
        events.append(payload["event"])

    llm = ScriptedLLM(delay_s=0.5)
    session = _session(llm, on_control=on_control, speak_opening=False, barge_in_min_ms=300)
    run = asyncio.create_task(session.run())
    await say_to(session)
    await wait_until(lambda: session.is_speaking)
    for _ in range(3):  # 60 ms click / cough
        await session.push_audio(loud())
    for _ in range(6):
        await session.push_audio(silence())
    assert len(await next_audio(session)) > 0
    assert "barge_in" not in events and llm.asked == ["ciao"]
    await session.close()
    await run


async def test_client_side_playback_still_counts_as_speaking() -> None:
    """Audio is sent faster than real time: the bot is 'speaking' until the client is done."""
    llm = ScriptedLLM()
    session = _session(llm, speak_opening=False)
    run = asyncio.create_task(session.run())
    await say_to(session)
    await next_audio(session)
    await wait_until(lambda: not session.speaking_event.is_set())  # generation finished...
    assert session.is_speaking  # ...but 200 ms chunks are still playing on the client
    await session._handle_barge_in()
    assert not session.is_speaking and session.audio_out_q.empty()
    await session.close()
    await run


async def test_reset_conversation_greets_again() -> None:
    llm = ScriptedLLM()
    session = _session(llm, speak_opening=True)
    run = asyncio.create_task(session.run())
    await next_audio(session)
    await session.reset_conversation()
    await wait_until(lambda: llm.resets == 1)
    assert len(await next_audio(session)) > 0
    assert session.tts.spoken.count("Benvenuto!") == 2  # type: ignore[attr-defined]
    await session.close()
    await run


class _ExplodingSTT(FakeSTT):
    async def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        raise RuntimeError("model crashed")


async def test_a_stt_failure_is_reported_and_the_call_continues() -> None:
    events: list[dict[str, str]] = []

    async def on_control(payload: dict[str, str]) -> None:
        events.append(payload)

    session = _session(ScriptedLLM(), stt=_ExplodingSTT(), on_control=on_control, speak_opening=False)
    run = asyncio.create_task(session.run())
    await say_to(session)
    await wait_until(lambda: any(e.get("detail") == "stt_failed" for e in events))
    session.stt = FakeSTT(fixed_text="ciao")  # the model "recovers"
    await say_to(session)
    assert len(await next_audio(session)) > 0
    await session.close()
    await run


class _BrokenLLM(ScriptedLLM):
    async def stream_reply(self, user_text: str) -> AsyncIterator[str]:
        raise RuntimeError("boom")
        yield ""  # pragma: no cover


async def test_an_llm_crash_does_not_kill_the_pipeline() -> None:
    session = _session(_BrokenLLM(), speak_opening=False)
    run = asyncio.create_task(session.run())
    await say_to(session)
    await asyncio.sleep(0.3)
    assert not run.done()  # the stages are still alive
    await session.close()
    await run


async def test_close_is_graceful_and_idempotent() -> None:
    session = _session(ScriptedLLM(delay_s=5.0), speak_opening=False)
    run = asyncio.create_task(session.run())
    await say_to(session)
    await wait_until(lambda: session.speaking_event.is_set())
    await asyncio.wait_for(session.close(), timeout=6.0)
    await session.close()
    await asyncio.wait_for(run, timeout=6.0)
    assert all(t.done() for t in session._tasks)
    await session.push_audio(loud())  # pushing after close is a no-op, not an error


async def test_end_of_stream_flushes_and_drains() -> None:
    session = _session(ScriptedLLM(), speak_opening=False)
    run = asyncio.create_task(session.run())
    for _ in range(12):
        await session.push_audio(loud())  # speech still in progress when the stream ends
    await session.push_audio(None)
    chunks = []
    while (chunk := await asyncio.wait_for(session.audio_out_q.get(), timeout=5.0)) is not None:
        chunks.append(chunk)  # the stream ends with a None marker for the writer
    assert chunks
    await asyncio.wait_for(run, timeout=10.0)
    await session.close()
