"""Abstract interfaces: VAD / STT / LLM orchestrator / TTS."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Literal


@dataclass(frozen=True, slots=True)
class VadEvent:
    kind: Literal["speech_start", "speech_end", "segment"]
    pcm: bytes = b""  # full utterance on speech_end/segment
    sample_rate: int = 16000


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class LlmCallbacks:
    on_token: str = ""  # reserved for future sync hooks


class AbstractVAD(ABC):
    """Voice activity detector over PCM16 frames."""

    @abstractmethod
    def process_frame(self, pcm: bytes, sample_rate: int) -> VadEvent | None:
        """Feed one frame; return an event when speech starts/ends."""
        raise NotImplementedError

    @abstractmethod
    def flush(self) -> VadEvent | None:
        """Flush buffered speech at end of stream."""
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        """Drop internal buffers (used on barge-in)."""
        raise NotImplementedError


class AbstractSTT(ABC):
    """Streaming-capable speech-to-text (local model)."""

    @abstractmethod
    async def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        """Transcribe one complete utterance (PCM16 mono)."""
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release model resources."""
        return None


class AbstractLLMOrchestrator(ABC):
    """Dialogue manager: PII-scrub -> BE (local LLM) -> function calls -> token stream."""

    history: list[ChatMessage]

    @abstractmethod
    async def stream_reply(self, user_text: str) -> AsyncIterator[str]:
        """Yield text tokens for one assistant turn. Must be cancellable."""
        raise NotImplementedError
        yield ""  # pragma: no cover - keeps method an async generator for subclasses

    @abstractmethod
    def reset(self) -> None:
        """Clear dialogue history."""
        raise NotImplementedError


class AbstractTTS(ABC):
    """Text-to-speech with streaming audio output (local model)."""

    sample_rate: int = 22050

    @abstractmethod
    async def synthesize_stream(
        self, text_stream: AsyncIterator[str]
    ) -> AsyncIterator[bytes]:
        """Yield PCM16LE audio chunks while text tokens arrive. Must be cancellable."""
        raise NotImplementedError
        yield b""  # pragma: no cover

    async def aclose(self) -> None:
        """Release model resources."""
        return None
