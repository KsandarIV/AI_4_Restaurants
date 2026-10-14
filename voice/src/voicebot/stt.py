"""Local STT backends (faster-whisper) + fake backend for CI/tests."""

from __future__ import annotations

import asyncio
import io
import wave

from .interfaces import AbstractSTT


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


class FasterWhisperSTT(AbstractSTT):
    """Local faster-whisper STT. Model is loaded lazily on first transcribe."""

    def __init__(
        self,
        model: str = "tiny",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "it",
    ) -> None:
        self._model_name = model
        self._device = device
        self._compute_type = compute_type
        self._language = language
        self._model: object | None = None
        self._lock = asyncio.Lock()

    def _ensure_model(self) -> object:
        if self._model is None:
            from faster_whisper import WhisperModel  # type: ignore[import-not-found]

            self._model = WhisperModel(self._model_name, device=self._device, compute_type=self._compute_type)
        return self._model

    async def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        """Transcribe utterance off the event loop (blocking inference in thread)."""
        if len(pcm) < 3200:  # <100 ms: ignore
            return ""
        model = self._ensure_model()
        wav = _pcm_to_wav(pcm, sample_rate)

        def _run() -> str:
            segments, _ = model.transcribe(wav, language=self._language, beam_size=1, vad_filter=False)  # type: ignore[union-attr]
            return "".join(s.text for s in segments).strip()

        return await asyncio.to_thread(_run)

    async def aclose(self) -> None:
        """Drop model reference (frees memory on next GC)."""
        self._model = None


class FakeSTT(AbstractSTT):
    """Deterministic STT for tests/offline runs (no model)."""

    def __init__(self, fixed_text: str = "vorrei prenotare un tavolo per due domani alle venti") -> None:
        self.fixed_text = fixed_text

    async def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        """Return fixed text for any non-silent utterance."""
        import array

        if not pcm:
            return ""
        arr = array.array("h")
        arr.frombytes(pcm)
        if not arr or max(abs(s) for s in arr) < 100:
            return ""
        return self.fixed_text


def build_stt(backend: str, **kwargs: object) -> AbstractSTT:
    """Factory: 'fake' or 'faster-whisper'."""
    if backend == "fake":
        text = str(kwargs.get("fixed_text", "vorrei prenotare un tavolo per due domani alle venti"))
        return FakeSTT(fixed_text=text)
    return FasterWhisperSTT(**kwargs)  # type: ignore[arg-type]
