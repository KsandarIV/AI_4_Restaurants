"""Local speech-to-text: faster-whisper, plus a scriptable fake for tests and offline runs."""

from __future__ import annotations

import array
import asyncio
from typing import Any

from .interfaces import AbstractSTT
from .logging_json import get_logger

log = get_logger("stt")

_MIN_PCM_BYTES = 3200  # < 100 ms at 16 kHz: nothing worth transcribing
_WHISPER_RATE = 16000
# Typical Whisper hallucinations on near-silence / noise (lower-cased, prefix match).
_HALLUCINATIONS = (
    "sottotitoli", "grazie a tutti", "iscriviti", "thanks for watching",
    "subtitles by", "amara.org", "like and subscribe",
)


def _pcm_to_float32(pcm: bytes, sample_rate: int) -> Any:
    """PCM16LE -> float32 mono at 16 kHz (the format faster-whisper consumes directly)."""
    import numpy as np

    audio = np.frombuffer(pcm[: len(pcm) - (len(pcm) % 2)], dtype=np.int16).astype(np.float32)
    audio /= 32768.0
    if sample_rate != _WHISPER_RATE and audio.size:
        target = int(audio.size * _WHISPER_RATE / sample_rate)
        audio = np.interp(
            np.linspace(0.0, audio.size - 1, target), np.arange(audio.size), audio
        ).astype(np.float32)
    return audio


class FasterWhisperSTT(AbstractSTT):
    """faster-whisper STT. The model is shared by all sessions and loaded once."""

    def __init__(
        self,
        model: str = "tiny",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "it",
        initial_prompt: str = "",
    ) -> None:
        self._model_name = model
        self._initial_prompt = initial_prompt
        self._device = device
        self._compute_type = compute_type
        self._language = language
        self._model: Any = None
        self._lock = asyncio.Lock()  # one inference at a time: CPU-bound, shared model

    def _ensure_model(self) -> Any:
        if self._model is None:
            from faster_whisper import WhisperModel

            log.info("loading whisper model=%s device=%s", self._model_name, self._device)
            self._model = WhisperModel(
                self._model_name, device=self._device, compute_type=self._compute_type
            )
        return self._model

    async def warmup(self) -> None:
        """Load the model and run a dummy inference (first call is otherwise very slow)."""
        def _run() -> None:
            model = self._ensure_model()
            segments, _ = model.transcribe(
                _pcm_to_float32(b"\x00\x00" * _WHISPER_RATE, _WHISPER_RATE),
                language=self._language, beam_size=1,
            )
            list(segments)

        await asyncio.to_thread(_run)

    async def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        """Transcribe one utterance off the event loop."""
        if len(pcm) < _MIN_PCM_BYTES:
            return ""
        audio = _pcm_to_float32(pcm, sample_rate)

        def _run() -> str:
            model = self._ensure_model()
            segments, _ = model.transcribe(
                audio,
                language=self._language,
                beam_size=1,
                vad_filter=False,
                condition_on_previous_text=False,
                initial_prompt=self._initial_prompt or None,
            )
            parts = [s.text for s in segments if getattr(s, "no_speech_prob", 0.0) < 0.6]
            return "".join(parts).strip()

        async with self._lock:
            text = await asyncio.to_thread(_run)
        echoed_prompt = bool(self._initial_prompt) and text.lower().startswith(
            self._initial_prompt.lower()[:24]
        )  # the prompt itself, "heard" in noise
        if echoed_prompt or text.lower().startswith(_HALLUCINATIONS):
            log.info("dropped likely whisper hallucination: %r", text[:60])
            return ""
        return text

    async def aclose(self) -> None:
        """Drop the model reference (memory is freed on the next GC)."""
        self._model = None


class FakeSTT(AbstractSTT):
    """Deterministic STT: returns scripted texts for any non-silent utterance.

    ``script`` is consumed one entry per utterance; the last entry repeats.
    """

    def __init__(
        self,
        fixed_text: str = "Vorrei prenotare un tavolo per due domani alle venti",
        script: list[str] | None = None,
    ) -> None:
        self.fixed_text = fixed_text
        self._script = list(script) if script else []

    async def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        """Return the next scripted text, or "" for silence."""
        if not pcm:
            return ""
        arr = array.array("h")
        arr.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
        if not arr or max(abs(s) for s in arr) < 100:
            return ""
        if self._script:
            return self._script.pop(0) if len(self._script) > 1 else self._script[0]
        return self.fixed_text


def build_stt(backend: str, **kwargs: Any) -> AbstractSTT:
    """Factory: ``fake`` or ``faster-whisper``."""
    if backend == "fake":
        return FakeSTT(
            fixed_text=str(kwargs.get("fixed_text", FakeSTT().fixed_text)),
            script=kwargs.get("script"),
        )
    allowed = {k: v for k, v in kwargs.items() if k in ("model", "device", "compute_type", "language", "initial_prompt")}
    return FasterWhisperSTT(**allowed)
