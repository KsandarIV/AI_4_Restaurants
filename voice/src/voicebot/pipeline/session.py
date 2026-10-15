"""Core real-time loop: producer-consumer over ``asyncio.Queue`` with barge-in.

Dataflow of one call (every queue is bounded: backpressure, never unbounded memory):

  WebSocket reader --PCM--> audio_in_q --> [VAD] --utterance--> segment_q
      --> [STT] --text--> text_q --> [LLM turn] --tokens--> [TTS] --PCM--> audio_out_q
      --> WebSocket writer

Barge-in: while the bot is speaking (or the client is still playing audio that was
sent faster than real time) any speech that lasts ``barge_in_min_ms`` cancels the running
turn, drops the queued audio and tells the client ``{"event": "barge_in"}``. The VAD is
NOT reset: it is already capturing the interrupting utterance, which is then answered.

Control events sent to the client (for the UI): ``heard`` (utterance captured),
``transcript`` (what STT understood), ``thinking`` (LLM working), ``reply`` (full text
of the answer), ``barge_in``, ``error``.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from ..audio import pcm_duration_s
from ..interfaces import AbstractLLMOrchestrator, AbstractSTT, AbstractTTS, AbstractVAD
from ..logging_json import get_logger

log = get_logger("session")

ControlCallback = Callable[[dict[str, str]], Awaitable[None] | None]
_RESET = chr(0) + "reset"  # in-band marker in text_q: cannot be produced by speech recognition


async def _single(text: str) -> AsyncIterator[str]:
    yield text


class VoiceSession:
    """One full-duplex voice conversation."""

    def __init__(
        self,
        vad: AbstractVAD,
        stt: AbstractSTT,
        llm: AbstractLLMOrchestrator,
        tts: AbstractTTS,
        sample_rate: int = 16000,
        audio_in_max: int = 200,
        text_max: int = 32,
        audio_out_max: int = 200,
        barge_in_enabled: bool = True,
        barge_in_min_ms: int = 300,
        stt_timeout_s: float = 30.0,
        on_control: ControlCallback | None = None,
        owns_models: bool = True,
        speak_opening: bool = True,
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
        self.barge_in_min_ms = barge_in_min_ms
        self.stt_timeout_s = stt_timeout_s
        self.on_control = on_control
        self.owns_models = owns_models  # False when STT/TTS are shared by all sessions
        self.speak_opening = speak_opening
        self.speaking_event = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []
        self._turn_task: asyncio.Task[None] | None = None
        self._gen = 0  # generation counter: invalidates stale work after a barge-in
        self._barge_pending = False  # speech started while the bot talked, not yet long enough
        self._playback_until = 0.0  # loop time when the client finishes playing what we sent
        self._closed = False
        self.llm.on_event = self._emit

    # ---------------- public API ----------------

    @property
    def is_speaking(self) -> bool:
        """True while the bot is generating *or the client is still playing* its speech."""
        if self.speaking_event.is_set():
            return True
        return asyncio.get_running_loop().time() < self._playback_until

    async def run(self) -> None:
        """Start all pipeline stages; returns when the call ends or a stage fails."""
        self._tasks = [
            asyncio.create_task(self._vad_loop(), name=f"vad-{self.session_id}"),
            asyncio.create_task(self._stt_loop(), name=f"stt-{self.session_id}"),
            asyncio.create_task(self._llm_loop(), name=f"llm-{self.session_id}"),
        ]
        try:
            done, pending = await asyncio.wait(self._tasks, return_when=asyncio.FIRST_EXCEPTION)
        except asyncio.CancelledError:
            for task in self._tasks:
                task.cancel()
            raise
        for task in done:
            if not task.cancelled() and task.exception() is not None:
                log.error("stage %s crashed: %r", task.get_name(), task.exception())
        for task in pending:
            task.cancel()

    async def push_audio(self, pcm: bytes | None) -> None:
        """Producer entry, called by the WebSocket reader. ``None`` = end of stream."""
        if self._closed:
            return
        try:
            self.audio_in_q.put_nowait(pcm)
        except asyncio.QueueFull:
            # Live audio: when we are late, the oldest frame is the one to lose.
            with contextlib.suppress(asyncio.QueueEmpty):
                self.audio_in_q.get_nowait()
            await self.audio_in_q.put(pcm)

    async def reset_conversation(self) -> None:
        """Start over (like "new conversation" in the chat bot): stop talking, greet again."""
        await self._handle_barge_in()
        self.vad.reset()
        await self.text_q.put(_RESET)

    async def next_output(self) -> bytes | None:
        """Consumer entry, called by the WebSocket writer. ``None`` = end of stream."""
        return await self.audio_out_q.get()

    async def close(self) -> None:
        """Graceful shutdown: poison pills, cancel tasks, join with a timeout."""
        if self._closed:
            return
        self._closed = True
        for queue in (self.audio_in_q, self.segment_q, self.text_q):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(None)
        tasks = [*self._tasks]
        if self._turn_task is not None:
            tasks.append(self._turn_task)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=5.0)
        closers: list[Callable[[], Awaitable[None]]] = [self.llm.aclose]
        if self.owns_models:
            closers += [self.stt.aclose, self.tts.aclose]
        for closer in closers:
            try:
                await asyncio.wait_for(closer(), timeout=5.0)
            except Exception as exc:  # noqa: BLE001 - shutdown must never raise
                log.warning("close error session=%s err=%r", self.session_id, exc)

    # ---------------- helpers ----------------

    async def _emit(self, payload: dict[str, str]) -> None:
        """Notify the client (UI states, transcripts). Never raises."""
        if self.on_control is None:
            return
        try:
            result: Any = self.on_control(payload)
            if asyncio.isfuture(result) or asyncio.iscoroutine(result):
                await result
        except Exception as exc:  # noqa: BLE001
            log.warning("control callback error session=%s err=%r", self.session_id, exc)

    # ---------------- stage 1: VAD ----------------

    async def _vad_loop(self) -> None:
        """Consume frames; emit utterances; detect barge-in."""
        while True:
            frame = await self.audio_in_q.get()
            if frame is None:  # end of stream: flush what is buffered
                event = self.vad.flush()
                if event and event.pcm:
                    await self.segment_q.put(event.pcm)
                await self.segment_q.put(None)
                return
            try:
                event = self.vad.process_frame(frame, self.sample_rate)
            except Exception as exc:  # noqa: BLE001 - a bad frame must not kill the call
                log.error("vad error session=%s err=%r", self.session_id, exc)
                continue

            if event is None:
                if self._barge_pending and self.vad.speech_ms >= self.barge_in_min_ms:
                    self._barge_pending = False
                    await self._handle_barge_in()
                continue
            if event.kind == "speech_start":
                self._barge_pending = self.barge_in_enabled and self.is_speaking
            elif event.kind == "speech_end" and event.pcm:
                if self._barge_pending:  # shorter than barge_in_min_ms: noise or echo
                    self._barge_pending = False
                    log.info("ignored short noise while speaking session=%s", self.session_id)
                    continue
                await self.segment_q.put(event.pcm)
                await self._emit({"event": "heard"})

    # ---------------- stage 2: STT ----------------

    async def _stt_loop(self) -> None:
        """Transcribe utterances -> ``text_q`` (empty transcripts are skipped)."""
        while True:
            segment = await self.segment_q.get()
            if segment is None:
                await self.text_q.put(None)
                return
            try:
                text = await asyncio.wait_for(
                    self.stt.transcribe(segment, self.sample_rate), timeout=self.stt_timeout_s
                )
            except asyncio.TimeoutError:
                log.warning("stt timeout session=%s", self.session_id)
                await self._emit({"event": "error", "detail": "stt_timeout"})
                continue
            except Exception as exc:  # noqa: BLE001
                log.error("stt error session=%s err=%r", self.session_id, exc)
                await self._emit({"event": "error", "detail": "stt_failed"})
                continue
            text = text.strip()
            if text:
                log.info("utterance transcribed session=%s chars=%d", self.session_id, len(text))
                await self._emit({"event": "transcript", "text": text})
                await self.text_q.put(text)

    # ---------------- stage 3: LLM + TTS ----------------

    async def _llm_loop(self) -> None:
        """Say the opening line, then answer each utterance in order."""
        if self.speak_opening:
            try:
                opening = await self.llm.opening()
            except Exception as exc:  # noqa: BLE001
                log.error("opening failed session=%s err=%r", self.session_id, exc)
                opening = ""
            if opening:
                await self._run_turn(_single(opening), thinking=False)
        while True:
            user_text = await self.text_q.get()
            if user_text is None:
                await self.audio_out_q.put(None)
                return
            if user_text == _RESET:
                self.llm.reset()
                opening = await self.llm.opening()
                if opening:
                    await self._run_turn(_single(opening), thinking=False)
                continue
            await self._run_turn(self.llm.stream_reply(user_text), thinking=True)

    async def _run_turn(self, tokens: AsyncIterator[str], thinking: bool) -> None:
        """Run one turn as its own task so a barge-in can cancel it at any moment."""
        task = asyncio.create_task(self._speak(tokens, thinking), name=f"turn-{self.session_id}")
        self._turn_task = task
        try:
            await asyncio.wait({task})
        except asyncio.CancelledError:  # the session is closing
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
            raise
        finally:
            if self._turn_task is task:
                self._turn_task = None
        if not task.cancelled() and task.exception() is not None:
            log.error("turn failed session=%s err=%r", self.session_id, task.exception())
            await self._emit({"event": "error", "detail": "turn_failed"})

    async def _speak(self, tokens: AsyncIterator[str], thinking: bool) -> None:
        """Stream ``tokens`` into the TTS and the TTS audio into ``audio_out_q``."""
        self._gen += 1
        gen = self._gen
        self.speaking_event.set()
        token_q: asyncio.Queue[str | None] = asyncio.Queue(maxsize=64)
        spoken: list[str] = []
        if thinking:
            await self._emit({"event": "thinking"})

        async def pump() -> None:
            try:
                async for token in tokens:
                    if gen != self._gen:
                        break  # stale turn after a barge-in
                    spoken.append(token)
                    await token_q.put(token)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.error("llm pump error session=%s err=%r", self.session_id, exc)
            finally:
                closer = getattr(tokens, "aclose", None)
                if closer is not None:
                    with contextlib.suppress(Exception):
                        await closer()
                with contextlib.suppress(asyncio.QueueFull):
                    token_q.put_nowait(None)

        async def token_iter() -> AsyncIterator[str]:
            while True:
                token = await token_q.get()
                if token is None:
                    return
                yield token

        pump_task = asyncio.create_task(pump(), name=f"pump-{self.session_id}")
        completed = False
        try:
            async for audio in self.tts.synthesize_stream(token_iter()):
                if gen != self._gen:
                    break  # a barge-in started a newer generation
                await self.audio_out_q.put(audio)
                loop = asyncio.get_running_loop()
                self._playback_until = max(self._playback_until, loop.time()) + pcm_duration_s(
                    audio, self.tts.sample_rate
                )
            completed = gen == self._gen
        finally:
            pump_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(asyncio.shield(pump_task), timeout=2.0)
            if gen == self._gen:
                self.speaking_event.clear()
        if completed and spoken:
            await self._emit({"event": "reply", "text": "".join(spoken)})
        log.info("turn end session=%s completed=%s", self.session_id, completed)

    async def _handle_barge_in(self) -> None:
        """Interrupt: invalidate the turn, cancel it, drop queued audio, tell the client."""
        self._gen += 1
        task = self._turn_task
        if task is not None and not task.done():
            task.cancel()
        drained = 0
        while True:
            try:
                self.audio_out_q.get_nowait()
                drained += 1
            except asyncio.QueueEmpty:
                break
        self._playback_until = 0.0
        self.speaking_event.clear()
        log.info("barge_in session=%s drained=%d", self.session_id, drained)
        await self._emit({"event": "barge_in"})
