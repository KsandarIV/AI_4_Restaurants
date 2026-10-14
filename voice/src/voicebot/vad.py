"""Energy + WebRTC VAD implementations (both local, no network)."""

from __future__ import annotations

from .audio import rms_int16
from .interfaces import VadEvent


class EnergyVAD:
    """Threshold VAD over RMS energy with hangover silence detection.

    Fully dependency-free; robust default for 16 kHz mono PCM.
    """

    def __init__(
        self,
        threshold: float = 500.0,
        silence_ms: int = 600,
        min_speech_ms: int = 250,
        max_segment_s: float = 15.0,
        sample_rate: int = 16000,
        frame_ms: int = 20,
    ) -> None:
        self.threshold = threshold
        self.silence_frames = max(1, int(silence_ms / frame_ms))
        self.min_speech_frames = max(1, int(min_speech_ms / frame_ms))
        self.max_segment_frames = max(1, int(max_segment_s * 1000 / frame_ms))
        self.sample_rate = sample_rate
        self._in_speech = False
        self._buffer = bytearray()
        self._silence_run = 0
        self._speech_frames = 0

    def process_frame(self, pcm: bytes, sample_rate: int) -> VadEvent | None:
        """Process one frame; emit start/end events."""
        energetic = rms_int16(pcm) >= self.threshold
        if not self._in_speech:
            if energetic:
                self._in_speech = True
                self._buffer = bytearray(pcm)
                self._silence_run = 0
                self._speech_frames = 1
                return VadEvent(kind="speech_start", sample_rate=sample_rate)
            return None
        # in speech
        self._buffer.extend(pcm)
        self._speech_frames += 1
        if energetic:
            self._silence_run = 0
        else:
            self._silence_run += 1
        if self._silence_run >= self.silence_frames or self._speech_frames >= self.max_segment_frames:
            seg = bytes(self._buffer)
            self.reset()
            if len(seg) >= self.min_speech_frames * len(pcm):
                return VadEvent(kind="speech_end", pcm=seg, sample_rate=sample_rate)
            return None
        return None

    def flush(self) -> VadEvent | None:
        """Emit buffered speech if it meets the minimum length."""
        if self._in_speech and self._speech_frames >= self.min_speech_frames:
            seg = bytes(self._buffer)
            self.reset()
            return VadEvent(kind="speech_end", pcm=seg, sample_rate=self.sample_rate)
        self.reset()
        return None

    def reset(self) -> None:
        """Clear buffers."""
        self._in_speech = False
        self._buffer = bytearray()
        self._silence_run = 0
        self._speech_frames = 0


class WebRtcVADWrapper:
    """webrtcvad-backed VAD with the same frame protocol.

    Requires the ``webrtcvad`` package and 10/20/30 ms frames at 8/16/32 kHz.
    """

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
            import webrtcvad  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("webrtcvad package not installed") from exc
        if frame_ms not in (10, 20, 30):
            raise ValueError("webrtcvad requires 10/20/30 ms frames")
        self._vad = webrtcvad.Vad(aggressiveness)
        self.silence_frames = max(1, int(silence_ms / frame_ms))
        self.min_speech_frames = max(1, int(min_speech_ms / frame_ms))
        self.max_segment_frames = max(1, int(max_segment_s * 1000 / frame_ms))
        self.sample_rate = sample_rate
        self._in_speech = False
        self._buffer = bytearray()
        self._silence_run = 0
        self._speech_frames = 0

    def _is_voiced(self, pcm: bytes, sample_rate: int) -> bool:
        try:
            return bool(self._vad.is_speech(pcm, sample_rate))
        except Exception:
            return rms_int16(pcm) >= 500.0

    def process_frame(self, pcm: bytes, sample_rate: int) -> VadEvent | None:
        """Classify with webrtcvad + hangover state machine on real audio."""
        voiced = self._is_voiced(pcm, sample_rate)
        if not self._in_speech:
            if voiced:
                self._in_speech = True
                self._buffer = bytearray(pcm)
                self._silence_run = 0
                self._speech_frames = 1
                return VadEvent(kind="speech_start", sample_rate=sample_rate)
            return None
        self._buffer.extend(pcm)
        self._speech_frames += 1
        self._silence_run = 0 if voiced else self._silence_run + 1
        if self._silence_run >= self.silence_frames or self._speech_frames >= self.max_segment_frames:
            seg = bytes(self._buffer)
            min_bytes = self.min_speech_frames * len(pcm)
            self.reset()
            if len(seg) >= min_bytes:
                return VadEvent(kind="speech_end", pcm=seg, sample_rate=sample_rate)
            return None
        return None

    def flush(self) -> VadEvent | None:
        """Emit buffered speech if long enough."""
        if self._in_speech and self._speech_frames >= self.min_speech_frames:
            seg = bytes(self._buffer)
            self.reset()
            return VadEvent(kind="speech_end", pcm=seg, sample_rate=self.sample_rate)
        self.reset()
        return None

    def reset(self) -> None:
        """Clear buffers."""
        self._in_speech = False
        self._buffer = bytearray()
        self._silence_run = 0
        self._speech_frames = 0


def build_vad(mode: str, **kwargs: object) -> EnergyVAD | WebRtcVADWrapper:
    """Factory selecting the VAD backend."""
    if mode == "webrtc":
        return WebRtcVADWrapper(**kwargs)  # type: ignore[arg-type]
    return EnergyVAD(**kwargs)  # type: ignore[arg-type]
