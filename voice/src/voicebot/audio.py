"""PCM audio helpers shared by VAD / STT / TTS / pipeline."""

from __future__ import annotations

import array
import io
import re
import wave
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AudioFrame:
    """One mono PCM16LE frame."""

    pcm: bytes
    sample_rate: int
    seq: int


def bytes_per_frame(sample_rate: int, frame_ms: int) -> int:
    """Return the expected byte length of one mono int16 frame."""
    samples = int(sample_rate * frame_ms / 1000)
    return samples * 2


def pcm_duration_s(pcm: bytes | int, sample_rate: int) -> float:
    """Duration in seconds of mono PCM16 audio (``pcm`` may be the byte length)."""
    size = pcm if isinstance(pcm, int) else len(pcm)
    return size / 2 / sample_rate if sample_rate > 0 else 0.0


def rms_int16(pcm: bytes) -> float:
    """Root-mean-square of PCM16LE bytes (no numpy dependency)."""
    if len(pcm) < 2:
        return 0.0
    arr = array.array("h")
    arr.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not arr:
        return 0.0
    total = sum(float(s) * float(s) for s in arr)
    return float((total / len(arr)) ** 0.5)


def pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap mono PCM16 bytes into a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


_SENTENCE_END = re.compile(r"(?<=[.!?;:\n])\s+")
_TERMINATORS = ".!?;:\n"


def split_sentences(text: str) -> list[str]:
    """Split text into speakable chunks on sentence boundaries."""
    parts = _SENTENCE_END.split(text.strip())
    return [p for p in (s.strip() for s in parts) if p]


class SentenceChunker:
    """Turn a token stream into complete sentences, as early as possible.

    The TTS must start speaking before the LLM has finished, but never in the
    middle of a sentence (bad prosody). Very short sentences ("Ok.") are merged
    with the next one for the same reason.
    """

    def __init__(self, min_chars: int = 12) -> None:
        self._min_chars = min_chars
        self._buffer = ""

    def feed(self, token: str) -> list[str]:
        """Add a token; return the sentences that are now complete."""
        self._buffer += token
        stripped = self._buffer.rstrip()
        if stripped[-1:] in _TERMINATORS and stripped:
            complete_text, remainder = stripped, ""
        else:
            boundary = None
            for boundary in _SENTENCE_END.finditer(self._buffer):  # keep the last one
                pass
            if boundary is None:
                return []
            complete_text = self._buffer[: boundary.start()]
            remainder = self._buffer[boundary.end() :]  # raw: keeps the spaces between tokens
        sentences = split_sentences(complete_text)
        if not sentences:
            self._buffer = remainder
            return []
        if len(" ".join(sentences)) < self._min_chars:  # too short to be its own utterance
            self._buffer = complete_text.strip() + " " + remainder
            return []
        self._buffer = remainder
        return sentences

    def flush(self) -> list[str]:
        """Return whatever text is left at the end of the stream."""
        rest, self._buffer = self._buffer.strip(), ""
        return [rest] if rest else []


_MARKDOWN = re.compile(r"[*_#`|<>~^]+")
_EMOJI = re.compile("[\U0001f000-\U0001faff☀-➿️]")
_BOOKING_CODE = re.compile(r"\bRES-([A-Z0-9]{4,10})\b")


def speakable(text: str) -> str:
    """Make a reply TTS-friendly: no markdown or emoji, booking codes spelled out."""
    text = _EMOJI.sub("", text)
    text = _BOOKING_CODE.sub(lambda m: "R E S, " + " ".join(m.group(1)), text)
    text = _MARKDOWN.sub(" ", text)
    return re.sub(r"[ \t]+", " ", text).strip()
