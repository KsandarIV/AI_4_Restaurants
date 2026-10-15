"""Abstract interfaces: VAD / STT / LLM orchestrator / TTS.

The pipeline (``pipeline/session.py``) only knows these contracts, so every stage
can be swapped (real model, fake for tests, remote service) without touching it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class VadEvent:
    """Boundary detected by a VAD."""

    kind: Literal["speech_start", "speech_end", "segment"]
    pcm: bytes = b""  # full utterance on speech_end / segment
    sample_rate: int = 16000


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One entry of the dialogue history."""

    role: Literal["system", "user", "assistant"]
    content: str


class AbstractVAD(ABC):
    """Voice activity detector over PCM16 frames."""

    @property
    @abstractmethod
    def speech_ms(self) -> float:
        """Milliseconds of the speech burst in progress (0 when idle)."""
        raise NotImplementedError

    @abstractmethod
    def process_frame(self, pcm: bytes, sample_rate: int) -> VadEvent | None:
        """Feed one frame; return an event when speech starts or ends."""
        raise NotImplementedError

    @abstractmethod
    def flush(self) -> VadEvent | None:
        """Flush buffered speech at end of stream."""
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        """Drop internal buffers."""
        raise NotImplementedError


class AbstractSTT(ABC):
    """Speech-to-text running on a local model."""

    @abstractmethod
    async def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        """Transcribe one complete utterance (PCM16 mono)."""
        raise NotImplementedError

    async def warmup(self) -> None:
        """Load the model eagerly so the first call is not slow (optional)."""
        return None

    async def aclose(self) -> None:
        """Release model resources."""
        return None


class AbstractLLMOrchestrator(ABC):
    """Dialogue manager: anonymise -> BE (local LLM) -> restore -> token stream.

    It must behave exactly like the chat bot, only the transport (voice) differs.
    """

    history: list[ChatMessage]
    # Set by the session: lets the conversation tell the UI about structured facts
    # (customer registered, reservation created/updated/cancelled).
    on_event: Callable[[dict[str, str]], Awaitable[None]] | None = None
    # True once the conversation decided to end the call (after its last sentence is spoken).
    ended: bool = False

    async def opening(self) -> str:
        """Text the bot says as soon as the call starts (empty = stay silent)."""
        return ""

    @abstractmethod
    def stream_reply(self, user_text: str) -> AsyncIterator[str]:
        """Yield text tokens for one assistant turn. Must be cancellable."""
        raise NotImplementedError

    async def reply(self, user_text: str) -> str:
        """One complete reply (used by the on-demand v2 mode)."""
        return "".join([token async for token in self.stream_reply(user_text)])

    @abstractmethod
    def reset(self) -> None:
        """Start a brand-new conversation."""
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release network resources (optional)."""
        return None


class AbstractTTS(ABC):
    """Text-to-speech running on a local model, with streaming audio output."""

    sample_rate: int = 22050

    @abstractmethod
    def synthesize_stream(self, text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
        """Yield PCM16LE audio chunks while text tokens arrive. Must be cancellable."""
        raise NotImplementedError

    async def warmup(self) -> None:
        """Load the voice eagerly so the first sentence is not slow (optional)."""
        return None

    async def aclose(self) -> None:
        """Release model resources."""
        return None
