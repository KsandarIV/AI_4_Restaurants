"""Core real-time loop: Producer-Consumer over asyncio.Queue with barge-in.

Queues (bounded -> backpressure instead of unbounded memory growth):
  audio_in_q   bytes (PCM16 frames from WebSocket producer)
  segment_q    bytes (complete utterances from VAD)
  text_q       str   (STT transcripts)
  tts_in_q     AsyncIterator[str] jobs -> serialized as token queues
  audio_out_q  bytes (PCM16 TTS chunks to WebSocket producer)

Barge-in: while the assistant is speaking (speaking_event set), any new
VAD speech_start cancels the active LLM/TTS tasks, clears audio_out_q and
notifies the client with a JSON {"event": "barge_in"} control message.
Graceful shutdown via `close()` + task cancellation with timeouts.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import AsyncIterator, Callable

from ..interfaces import AbstractLLMOrchestrator, AbstractSTT, AbstractTTS
from ..logging_json import get_logger
from ..vad import EnergyVAD

log = get_logger("session")

ControlSender = Callable[[dict[str, str]], "asyncio.Future[None] | None"]


class VoiceSession:
    """One full-duplex voice conversation."""

    def __init__(
        self,
        vad: EnergyVAD,
        stt: AbstractSTT,
        llm: AbstractLLMOrchestrator,
        tts: AbstractTTS,
        sample_rate: int = 16000,
        audio_in_max: int = 200,
        text_max: int = 32,
        audio_out_max: int = 200,
        barge_in_enabled: bool = True,
        on_control: Callable[[dict[str, str]], asyncio.Future[object] | object | None] | None = None,
    ) -> None:
        self.session_id = uuid.uuid4().hex[:8]
        self.vad = vad
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.sample_rate = sample_rate
        self.audio_in_q: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=audio_in_max)
        self.segment_q: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=text_max)
        self.text_q: asyncio.Queue[str | None] = asyncio.Queue(maxsize=text_max)
        self.audio_out_q: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=audio_out_max)
        self.barge_in_enabled = barge_in_enabled
        self.on_control = on_control
        self.speaking_event = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []
        self._gen = 0  # generation counter: invalidates stale TTS/LLM work after barge-in
        self._closed = False

    # ---------------- public API ----------------

    async def run(self) -> None:
        """Start all pipeline stages; returns when closed or on fatal error."""
        self._tasks = [
            asyncio.create_task(self._vad_loop(), name=f"vad-{self.session_id}"),
            asyncio.create_task(self._stt_loop(), name=f"stt-{self.session_id}"),
            asyncio.create_task(self._llm_loop(), name=f"llm-{self.session_id}"),
        ]
        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            pass

    async def push_audio(self, pcm: bytes | None) -> None:
        """Producer entry: called by the WebSocket reader. None = EOS."""
        if self._closed:
            return
        try:
            self.audio_in_q.put_nowait(pcm)
        except asyncio.QueueFull:
            try:
                _ = self.audio_in_q.get_nowait()
            except asyncio.QueueEmpty:
                pass
            await self.audio_in_q.put(pcm)

    async def next_output(self) -> bytes | None:
        """Consumer entry: called by the WebSocket writer. None = EOS."""
        return await self.audio_out_q.get()

    async def close(self) -> None:
        """Graceful shutdown: poison pills, cancel, join with timeout."""
        if self._closed:
            return
        self._closed = True
        for q in (self.audio_in_q, self.segment_q, self.text_q):
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass
        for t in self._tasks:
            t.cancel()
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=5.0)
        for closer in (self.stt.aclose, self.tts.aclose):
            try:
                await asyncio.wait_for(closer(), timeout=5.0)
            except Exception as exc:  # noqa: BLE001 - shutdown must not raise
                log.warning("close error session=%s err=%s", self.session_id, exc)

    # ---------------- stages ----------------

    async def _vad_loop(self) -> None:
        """Consume frames; emit segments; detect barge-in on speech_start."""
        try:
            while True:
                frame = await self.audio_in_q.get()
                if frame is None:
                    event = self.vad.flush()
                    if event and event.pcm:
                        await self.segment_q.put(event.pcm)
                    await self.segment_q.put(None)
                    return
                try:
                    event = await asyncio.to_thread(self.vad.process_frame, frame, self.sample_rate)
                except Exception as exc:
                    log.error("vad error session=%s err=%s", self.session_id, exc)
                    continue
                if event is None:
                    continue
                if event.kind == "speech_start" and self.barge_in_enabled and self.speaking_event.is_set():
                    await self._handle_barge_in()
                elif event.kind == "speech_end" and event.pcm:
                    await self.segment_q.put(event.pcm)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("vad_loop fatal session=%s err=%s", self.session_id, exc)
            await self.segment_q.put(None)

    async def _stt_loop(self) -> None:
        """Transcribe segments -> text_q (skips empty transcripts)."""
        try:
            while True:
                segment = await self.segment_q.get()
                if segment is None:
                    await self.text_q.put(None)
                    return
                try:
                    text = await asyncio.wait_for(
                        self.stt.transcribe(segment, self.sample_rate), timeout=30.0
                    )
                except asyncio.TimeoutError:
                    log.warning("stt timeout session=%s", self.session_id)
                    continue
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.error("stt error session=%s err=%s", self.session_id, exc)
                    continue
                if text.strip():
                    await self.text_q.put(text.strip())
        except asyncio.CancelledError:
            raise

    async def _llm_loop(self) -> None:
        """Stream LLM tokens -> TTS -> audio_out_q (cancellable per turn)."""
        try:
            while True:
                user_text = await self.text_q.get()
                if user_text is None:
                    await self.audio_out_q.put(None)
                    return
                await self._speak_turn(user_text)
        except asyncio.CancelledError:
            raise

    async def _speak_turn(self, user_text: str) -> None:
        """One assistant turn with token->audio streaming and barge-in support."""
        self._gen += 1
        gen = self._gen
        token_q: asyncio.Queue[str | None] = asyncio.Queue(maxsize=64)
        self.speaking_event.set()
        log.info("turn start session=%s text=%r", self.session_id, user_text[:120])

        async def pump_tokens() -> None:
            try:
                async for token in self.llm.stream_reply(user_text):
                    if gen != self._gen:
                        break  # stale turn after barge-in
                    await token_q.put(token)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("llm pump error session=%s err=%s", self.session_id, exc)
            finally:
                try:
                    token_q.put_nowait(None)
                except asyncio.QueueFull:
                    pass

        async def token_iter() -> AsyncIterator[str]:
            while True:
                tok = await token_q.get()
                if tok is None:
                    return
                yield tok

        pump = asyncio.create_task(pump_tokens())
        try:
            async for audio in self.tts.synthesize_stream(token_iter()):
                if gen != self._gen:
                    break  # dropped: barge-in started a newer turn
                try:
                    self.audio_out_q.put_nowait(audio)
                except asyncio.QueueFull:
                    try:
                        _ = self.audio_out_q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    await self.audio_out_q.put(audio)
        except asyncio.CancelledError:
            pump.cancel()
            raise
        finally:
            if not pump.done():
                pump.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(pump), timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            except Exception as exc:
                log.warning("pump join err session=%s err=%s", self.session_id, exc)
            if gen == self._gen:
                self.speaking_event.clear()
            log.info("turn end session=%s", self.session_id)

    async def _handle_barge_in(self) -> None:
        """Interrupt playback: bump generation, drop queued audio, reset VAD/STT state."""
        self._gen += 1
        self.vad.reset()
        drained = 0
        while True:
            try:
                self.audio_out_q.get_nowait()
                drained += 1
            except asyncio.QueueEmpty:
                break
        self.speaking_event.clear()
        log.info("barge_in session=%s drained=%d", self.session_id, drained)
        if self.on_control is not None:
            try:
                res = self.on_control({"event": "barge_in"})
                if asyncio.isfuture(res) or asyncio.iscoroutine(res):
                    await res  # type: ignore[no-any-return]
            except Exception as exc:
                log.warning("control cb err session=%s err=%s", self.session_id, exc)
