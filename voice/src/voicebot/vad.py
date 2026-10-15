"""Energy and WebRTC voice activity detectors (both local, no network).

Both share one state machine (``_FrameVAD``): they only differ in how a single
frame is classified as voiced / unvoiced.
"""

from __future__ import annotations

from abc import abstractmethod

from .audio import rms_int16
from .interfaces import AbstractVAD, VadEvent


class _FrameVAD(AbstractVAD):
    """Frame classifier + hangover state machine producing start/end events.

    Time is measured from the audio actually received, not from a nominal frame size:
    the browser sends 2048-sample chunks (128 ms), the Python client 20 ms ones, and the
    pause detection must last the same ``silence_ms`` for both.
    """

    def __init__(
        self,
        silence_ms: int = 600,
        min_speech_ms: int = 250,
        max_segment_s: float = 15.0,
        sample_rate: int = 16000,
        frame_ms: int = 20,
    ) -> None:
        self.frame_ms = frame_ms  # nominal; only used by classifiers that need fixed frames
        self.silence_ms = float(silence_ms)
        self.min_speech_ms = float(min_speech_ms)
        self.max_segment_ms = max_segment_s * 1000.0
        self.sample_rate = sample_rate
        self._in_speech = False
        self._buffer = bytearray()
        self._speech_total_ms = 0.0  # since speech started, silence included
        self._silence_run_ms = 0.0  # trailing silence

    @abstractmethod
    def _is_voiced(self, pcm: bytes, sample_rate: int) -> bool:
        """Classify one chunk."""
        raise NotImplementedError

    @property
    def speech_ms(self) -> float:
        """Duration of the speech burst in progress (trailing silence excluded)."""
        return max(0.0, self._speech_total_ms - self._silence_run_ms) if self._in_speech else 0.0

    def process_frame(self, pcm: bytes, sample_rate: int) -> VadEvent | None:
        """Process one chunk of audio; emit ``speech_start`` / ``speech_end`` events."""
        voiced = self._is_voiced(pcm, sample_rate)
        duration_ms = len(pcm) / 2 / sample_rate * 1000.0 if sample_rate > 0 else 0.0
        if not self._in_speech:
            if not voiced:
                return None
            self._in_speech = True
            self._buffer = bytearray(pcm)
            self._silence_run_ms = 0.0
            self._speech_total_ms = duration_ms
            return VadEvent(kind="speech_start", sample_rate=sample_rate)

        self._buffer.extend(pcm)
        self._speech_total_ms += duration_ms
        self._silence_run_ms = 0.0 if voiced else self._silence_run_ms + duration_ms
        too_long = self._speech_total_ms >= self.max_segment_ms
        if self._silence_run_ms < self.silence_ms and not too_long:
            return None

        segment = bytes(self._buffer)
        long_enough = self.speech_ms >= self.min_speech_ms
        self.reset()
        if not long_enough:
            return None  # a click or cough: ignored
        return VadEvent(kind="speech_end", pcm=segment, sample_rate=sample_rate)

    def flush(self) -> VadEvent | None:
        """Emit the buffered speech at end of stream if it is long enough."""
        if self._in_speech and self.speech_ms >= self.min_speech_ms:
            segment = bytes(self._buffer)
            self.reset()
            return VadEvent(kind="speech_end", pcm=segment, sample_rate=self.sample_rate)
        self.reset()
        return None

    def reset(self) -> None:
        """Clear buffers."""
        self._in_speech = False
        self._buffer = bytearray()
        self._speech_total_ms = 0.0
        self._silence_run_ms = 0.0


class EnergyVAD(_FrameVAD):
    """RMS-threshold VAD: dependency-free and a robust default for 16 kHz mono PCM."""

    def __init__(
        self,
        threshold: float = 500.0,
        silence_ms: int = 600,
        min_speech_ms: int = 250,
        max_segment_s: float = 15.0,
        sample_rate: int = 16000,
        frame_ms: int = 20,
    ) -> None:
        super().__init__(silence_ms, min_speech_ms, max_segment_s, sample_rate, frame_ms)
        self.threshold = threshold

    def _is_voiced(self, pcm: bytes, sample_rate: int) -> bool:
        return rms_int16(pcm) >= self.threshold


class WebRtcVADWrapper(_FrameVAD):
    """``webrtcvad``-backed VAD (needs 10/20/30 ms frames at 8/16/32 kHz)."""

    def __init__(
        self,
        aggressiveness: int = 2,
        silence_ms: int = 600,
        min_speech_ms: int = 250,
        max_segment_s: float = 15.0,
        sample_rate: int = 16000,
        frame_ms: int = 20,
    ) -> None:
        try:
            import webrtcvad
        except ImportError as exc:
            raise RuntimeError("webrtcvad package not installed (use VAD_MODE=energy)") from exc
        if frame_ms not in (10, 20, 30):
            raise ValueError("webrtcvad requires 10/20/30 ms frames")
        super().__init__(silence_ms, min_speech_ms, max_segment_s, sample_rate, frame_ms)
        self._vad = webrtcvad.Vad(aggressiveness)

    def _is_voiced(self, pcm: bytes, sample_rate: int) -> bool:
        """webrtcvad only accepts exact 10/20/30 ms frames: cut the chunk into 20 ms pieces."""
        step = int(sample_rate * 0.02) * 2
        pieces = [pcm[i : i + step] for i in range(0, len(pcm) - step + 1, step)] or [pcm]
        voiced = 0
        for piece in pieces:
            try:
                voiced += bool(self._vad.is_speech(piece, sample_rate))
            except Exception:  # malformed length: fall back to energy for this piece
                voiced += rms_int16(piece) >= 500.0
        return voiced * 2 >= len(pieces)  # at least half of the pieces are voiced


def build_vad(mode: str, **kwargs: float | int) -> AbstractVAD:
    """Factory selecting the VAD backend.

    ``threshold`` only applies to the energy VAD and is dropped for webrtc.
    """
    if mode == "webrtc":
        kwargs.pop("threshold", None)
        return WebRtcVADWrapper(**kwargs)  # type: ignore[arg-type]
    return EnergyVAD(**kwargs)  # type: ignore[arg-type]
