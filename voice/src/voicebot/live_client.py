"""Headless client for the live mode: local microphone and speaker <-> ``/ws/voice``.

Browsers refuse the microphone on plain-HTTP LAN addresses; this client does not: run
it on any PC and it streams the local mic to the voice server and plays what comes back,
with automatic reconnection (exponential backoff) if the network or the server drops.

    python -m voicebot.live_client                      # ws://localhost:8003/ws/voice
    python -m voicebot.live_client ws://10.10.0.7:8003/ws/voice
    python -m voicebot.live_client --half-duplex        # no headphones: mute mic while playing

Without headphones the speaker is heard by the microphone and interrupts the bot:
use headphones, or ``--half-duplex`` (you cannot barge in, but there is no echo).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import threading
from collections.abc import Callable
from typing import Any, Protocol

import websockets

from .config import get_settings
from .logging_json import get_logger

log = get_logger("live_client")
EventHandler = Callable[[dict[str, Any]], None]


class Speaker(Protocol):
    """Where the bot's audio goes."""

    def play(self, pcm: bytes, sample_rate: int) -> None: ...
    def clear(self) -> None: ...
    @property
    def busy(self) -> bool: ...
    def close(self) -> None: ...


class LiveClient:
    """One persistent voice call that survives disconnections."""

    def __init__(
        self,
        url: str,
        frames: asyncio.Queue[bytes | None],
        speaker: Speaker,
        on_event: EventHandler | None = None,
        max_retries: int | None = None,
        half_duplex: bool = False,
        frame_bytes: int = 640,
        base_delay_s: float = 0.5,
    ) -> None:
        self.url = url
        self.frames = frames  # filled by the microphone; None = hang up
        self.speaker = speaker
        self.on_event = on_event or (lambda event: None)
        self.max_retries = max_retries  # None = retry forever
        self.half_duplex = half_duplex
        self.base_delay_s = base_delay_s
        self._silence = bytes(frame_bytes)
        self._tts_rate = 22050
        self.connections = 0  # how many times we (re)connected: handy in tests
        self._stopped = asyncio.Event()

    def stop(self) -> None:
        """Hang up: ends ``run()`` even while it is waiting to reconnect."""
        self._stopped.set()

    async def run(self) -> None:
        """Connect, stream, and reconnect with backoff until hung up."""
        attempt = 0
        while not self._stopped.is_set():
            hung_up = False
            try:
                async with websockets.connect(self.url, max_size=None, open_timeout=5) as ws:
                    self.connections += 1
                    attempt = 0
                    log.info("connected to %s", self.url)
                    hung_up = await self._call(ws)
            except (OSError, websockets.WebSocketException, asyncio.TimeoutError) as exc:
                log.warning("connection failed: %r", exc)
            if hung_up:
                return
            attempt += 1
            if self.max_retries is not None and attempt > self.max_retries:
                raise ConnectionError(f"cannot reach {self.url} after {self.max_retries} retries")
            delay = min(self.base_delay_s * 2.0 ** (attempt - 1), 8.0)
            log.info("reconnecting in %.1fs (attempt %d)", delay, attempt)
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._stopped.wait(), timeout=delay)

    async def _call(self, ws: Any) -> bool:
        """Stream until the connection ends. True = the user hung up (do not reconnect)."""
        sender = asyncio.create_task(self._send_loop(ws))
        receiver = asyncio.create_task(self._receive_loop(ws))
        try:
            done, _ = await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (sender, receiver):
                task.cancel()
            for task in (sender, receiver):
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        return sender in done and sender.result() is True

    async def _send_loop(self, ws: Any) -> bool:
        while True:
            frame = await self.frames.get()
            if frame is None:
                await ws.send(json.dumps({"cmd": "eos"}))
                return True
            if self.half_duplex and self.speaker.busy:
                frame = self._silence if len(frame) == len(self._silence) else bytes(len(frame))
            await ws.send(frame)

    async def _receive_loop(self, ws: Any) -> None:
        async for message in ws:
            if isinstance(message, bytes):
                self.speaker.play(message, self._tts_rate)
                continue
            try:
                event = json.loads(message)
            except ValueError:
                continue
            if event.get("event") == "ready" and event.get("tts_sample_rate"):
                self._tts_rate = int(event["tts_sample_rate"])
            elif event.get("event") == "barge_in":
                self.speaker.clear()
            self.on_event(event)


class SoundDeviceSpeaker:
    """Plays PCM16 through ``sounddevice`` with an instantly clearable buffer."""

    def __init__(self) -> None:
        import sounddevice as sd

        self._sd = sd
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._stream: Any = None
        self._rate = 0

    def _open(self, rate: int) -> None:
        if self._stream is not None and self._rate == rate:
            return
        if self._stream is not None:
            self._stream.close()
        self._rate = rate
        self._stream = self._sd.RawOutputStream(
            samplerate=rate, channels=1, dtype="int16", callback=self._fill
        )
        self._stream.start()

    def _fill(self, outdata: Any, frames: int, time: Any, status: Any) -> None:
        need = frames * 2
        with self._lock:
            chunk = bytes(self._buffer[:need])
            del self._buffer[:need]
        outdata[:] = chunk + bytes(need - len(chunk))  # pad with silence

    def play(self, pcm: bytes, sample_rate: int) -> None:
        """Queue audio for playback."""
        self._open(sample_rate)
        with self._lock:
            self._buffer.extend(pcm)

    def clear(self) -> None:
        """Drop everything not yet played (barge-in)."""
        with self._lock:
            self._buffer.clear()

    @property
    def busy(self) -> bool:
        """True while queued audio remains."""
        with self._lock:
            return len(self._buffer) > 0

    def close(self) -> None:
        """Stop the audio stream."""
        if self._stream is not None:
            self._stream.close()
            self._stream = None


async def _mic_to_queue(frames: asyncio.Queue[bytes | None], sample_rate: int, frame_ms: int) -> None:
    """Feed ``frames`` from the default microphone; drops the oldest frame when full."""
    import sounddevice as sd

    loop = asyncio.get_running_loop()
    block = int(sample_rate * frame_ms / 1000)

    def push(data: bytes) -> None:
        if frames.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                frames.get_nowait()
        frames.put_nowait(data)

    def callback(indata: Any, count: int, time: Any, status: Any) -> None:
        loop.call_soon_threadsafe(push, bytes(indata))

    with sd.RawInputStream(
        samplerate=sample_rate, channels=1, dtype="int16", blocksize=block, callback=callback
    ):
        await asyncio.Event().wait()  # until cancelled


def _print_event(event: dict[str, Any]) -> None:
    kind = event.get("event")
    if kind == "transcript":
        print(f"you: {event.get('text')}")
    elif kind == "reply":
        print(f"bot: {event.get('text')}")
    elif kind in ("barge_in", "error", "loading"):
        print(f"[{kind}] {event.get('detail', '')}")


async def amain(args: argparse.Namespace) -> int:
    """Run the call until Ctrl+C."""
    settings = get_settings()
    url = args.url or f"ws://localhost:{settings.voice_port}{settings.input_ws_path}"
    frames: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=100)
    speaker = SoundDeviceSpeaker()
    client = LiveClient(url, frames, speaker, _print_event, half_duplex=args.half_duplex,
                        frame_bytes=int(settings.sample_rate * settings.frame_ms / 1000) * 2)
    print(f"[live] {url}  (Ctrl+C to hang up{', half-duplex' if args.half_duplex else ''})")
    mic = asyncio.create_task(_mic_to_queue(frames, settings.sample_rate, settings.frame_ms))
    try:
        await client.run()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    except ConnectionError as exc:
        print(f"[live] {exc}")
        return 1
    finally:
        mic.cancel()
        speaker.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m voicebot.live_client``."""
    parser = argparse.ArgumentParser(prog="voicebot.live_client", description="Live voice call from this PC")
    parser.add_argument("url", nargs="?", help="ws://host:8003/ws/voice (default: this PC)")
    parser.add_argument("--half-duplex", action="store_true", help="mute the mic while the bot speaks")
    try:
        return asyncio.run(amain(parser.parse_args(argv)))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
