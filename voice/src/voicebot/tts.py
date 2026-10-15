"""Local text-to-speech: Piper (sentence-chunked streaming) and a fake tone generator."""

from __future__ import annotations

import asyncio
import io
import math
import struct
import threading
import wave
from abc import abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from .audio import SentenceChunker, speakable
from .config import resolve_path
from .interfaces import AbstractTTS
from .logging_json import get_logger

log = get_logger("tts")


class _SentenceTTS(AbstractTTS):
    """Shared streaming logic: text tokens -> complete sentences -> audio chunks.

    Audio for a sentence is produced as soon as the sentence is complete, i.e.
    while the LLM is still generating the rest of the reply.
    """

    @abstractmethod
    def _synth(self, sentence: str) -> bytes:
        """Blocking synthesis of one sentence to PCM16LE (runs in a worker thread)."""
        raise NotImplementedError

    async def synthesize_stream(self, text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
        """Yield one audio chunk per sentence while tokens arrive (cancellable)."""
        chunker = SentenceChunker()
        async for token in text_stream:
            for sentence in chunker.feed(token):
                audio = await self._speak(sentence)
                if audio:
                    yield audio
        for sentence in chunker.flush():
            audio = await self._speak(sentence)
            if audio:
                yield audio

    async def _speak(self, sentence: str) -> bytes:
        text = speakable(sentence)
        if not text:
            return b""
        return await asyncio.to_thread(self._synth, text)


class FakeTTS(_SentenceTTS):
    """Offline TTS: a 200 ms 440 Hz tone per sentence. Keeps the pipeline testable."""

    def __init__(self, sample_rate: int = 22050) -> None:
        self.sample_rate = sample_rate
        self.spoken: list[str] = []  # what would have been said (asserted in tests)

    def _synth(self, sentence: str) -> bytes:
        self.spoken.append(sentence)
        n = int(self.sample_rate * 0.2)
        return b"".join(
            struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440.0 * i / self.sample_rate)))
            for i in range(n)
        )


class PiperTTS(_SentenceTTS):
    """Piper TTS. Works with both the old (<=1.2) and the new (>=1.3) piper-tts API."""

    def __init__(self, model_path: str, config_path: str = "", sample_rate: int = 22050) -> None:
        self._model_path = model_path
        self._config_path = config_path
        self.sample_rate = sample_rate
        self._voice: Any = None
        self._lock = threading.Lock()  # espeak phonemizer is not thread-safe

    def _ensure_voice(self) -> Any:
        if self._voice is None:
            from piper import PiperVoice

            model = resolve_path(self._model_path)
            if not model.is_file():
                raise FileNotFoundError(
                    f"Piper model not found: {self._model_path} (looked in cwd, repo root, voice/). "
                    "Run `python setup/setup_env.py` or set PIPER_MODEL_PATH."
                )
            config = resolve_path(self._config_path) if self._config_path else None
            log.info("loading piper voice %s", model)
            self._voice = PiperVoice.load(str(model), config_path=str(config) if config else None)
            # The model dictates the rate: announce the real one, not the configured guess.
            self.sample_rate = int(self._voice.config.sample_rate)
        return self._voice

    async def warmup(self) -> None:
        """Load the voice and synthesise a short phrase (ONNX init is slow on first use)."""
        def _run() -> None:
            self._ensure_voice()
            self._synth("Pronto.")

        await asyncio.to_thread(_run)

    def _synth(self, sentence: str) -> bytes:
        with self._lock:
            return self._synth_locked(sentence)

    def _synth_locked(self, sentence: str) -> bytes:
        voice = self._ensure_voice()
        if hasattr(voice, "synthesize_wav"):  # piper-tts >= 1.3: iterator of AudioChunk
            return b"".join(chunk.audio_int16_bytes for chunk in voice.synthesize(sentence))
        buf = io.BytesIO()  # piper-tts <= 1.2: writes into a wave file
        with wave.open(buf, "wb") as wf:
            voice.synthesize(sentence, wf)
        buf.seek(0)
        with wave.open(buf, "rb") as wf:
            return bytes(wf.readframes(wf.getnframes()))

    async def aclose(self) -> None:
        """Release the voice model."""
        self._voice = None


def build_tts(backend: str, **kwargs: Any) -> AbstractTTS:
    """Factory: ``fake`` or ``piper``."""
    if backend == "fake":
        return FakeTTS(sample_rate=int(kwargs.get("sample_rate", 22050)))
    allowed = {k: v for k, v in kwargs.items() if k in ("model_path", "config_path", "sample_rate")}
    return PiperTTS(**allowed)
