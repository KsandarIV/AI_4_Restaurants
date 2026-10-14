"""PCM audio helpers shared by VAD/STT/TTS/pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AudioFrame:
    """One mono PCM16LE frame."""

    pcm: bytes
    sample_rate: int
    seq: int


def bytes_per_frame(sample_rate: int, frame_ms: int) -> int:
    """Return expected byte length of one mono int16 frame."""
    samples = int(sample_rate * frame_ms / 1000)
    return samples * 2


def rms_int16(pcm: bytes) -> float:
    """Root-mean-square of PCM16LE bytes (no numpy dependency)."""
    import array

    if not pcm:
        return 0.0
    arr = array.array("h")
    arr.frombytes(pcm)
    if not arr:
        return 0.0
    total = sum(float(s) * float(s) for s in arr)
    return (total / len(arr)) ** 0.5


def split_sentences(text: str) -> list[str]:
    """Split streamed text into speakable chunks on sentence boundaries."""
    import re

    parts = re.split(r"(?<=[.!?;:\n])\s+", text.strip())
    return [p for p in (s.strip() for s in parts) if p]
