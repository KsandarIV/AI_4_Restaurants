"""Local TTS backends: Piper (streaming, sentence-chunked) + fake sine generator."""

from __future__ import annotations

import asyncio
import math
import struct
from typing import AsyncIterator

from .audio import split_sentences
from .interfaces import AbstractTTS


class FakeTTS(AbstractTTS):
    """Offline TTS stub generating a short beep per sentence (keeps pipeline testable)."""

    def __init__(self, sample_rate: int = 22050) -> None:
        self.sample_rate = sample_rate

    async def synthesize_stream(self, text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
        """Yield 200 ms 440 Hz sine per received sentence."""
        buffer = ""
        async for token in text_stream:
            buffer += token
            sentences = split_sentences(buffer)
            if len(sentences) >= 2 or (buffer and buffer.strip()[-1:] in ".!?"):
                for sent in sentences:
                    yield self._tone(ms=200)
                buffer = ""
        if buffer.strip():
            yield self._tone(ms=200)

    def _tone(self, ms: int = 200, freq: float = 440.0) -> bytes:
        n = int(self.sample_rate * ms / 1000)
        return b"".join(
            struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * i / self.sample_rate)))
            for i in range(n)
        )


class PiperTTS(AbstractTTS):
    """Local Piper TTS with true token->audio streaming.

    Consumes the LLM token iterator, accumulates complete sentences and
    synthesizes each sentence in a worker thread so audio starts flowing
    before the LLM finishes (low perceived latency).
    """

    def __init__(self, model_path: str, config_path: str = "", sample_rate: int = 22050) -> None:
        self._model_path = model_path
        self._config_path = config_path
        self.sample_rate = sample_rate
        self._voice: object | None = None

    def _ensure_voice(self) -> object:
        if self._voice is None:
            from piper import PiperVoice  # type: ignore[import-not-found]

            self._voice = PiperVoice.load(self._model_path, config_path=self._config_path or None)
        return self._voice

    def _synth_sentence(self, sentence: str) -> bytes:
        import io
        import wave

        voice = self._ensure_voice()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            voice.synthesize(sentence, wf)  # type: ignore[union-attr]
        buf.seek(0)
        with wave.open(buf, "rb") as wf:
            raw = wf.readframes(wf.getnframes())
            self.sample_rate = wf.getframerate()
            return bytes(raw)

    async def synthesize_stream(self, text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
        """Synthesize sentence-by-sentence as tokens arrive (cancellable)."""
        buffer = ""
        async for token in text_stream:
            buffer += token
            sentences = split_sentences(buffer)
            if len(sentences) >= 2 or (buffer.strip() and buffer.strip()[-1] in ".!?;:\n"):
                complete = " ".join(sentences[:-1]) if buffer.strip()[-1] not in ".!?;:\n" else " ".join(sentences)
                remainder = "" if buffer.strip()[-1] in ".!?;:\n" else sentences[-1]
                if complete:
                    yield await asyncio.to_thread(self._synth_sentence, complete)
                buffer = remainder
        if buffer.strip():
            yield await asyncio.to_thread(self._synth_sentence, buffer.strip())

    async def aclose(self) -> None:
        """Release voice model."""
        self._voice = None


def build_tts(backend: str, **kwargs: object) -> AbstractTTS:
    """Factory: 'fake' or 'piper'."""
    if backend == "fake":
        return FakeTTS(sample_rate=int(kwargs.get("sample_rate", 22050)))  # type: ignore[arg-type]
    return PiperTTS(**kwargs)  # type: ignore[arg-type]
