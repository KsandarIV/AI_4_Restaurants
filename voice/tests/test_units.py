"""VAD + PII + audio helper tests (no models required)."""

from __future__ import annotations

import struct

from voicebot.audio import bytes_per_frame, rms_int16, split_sentences
from voicebot.pii import scrub_pii
from voicebot.vad import EnergyVAD


def _frame(val: int, n: int = 320) -> bytes:
    return struct.pack("<%dh" % n, *([val] * n))


def test_vad_segments_speech() -> None:
    vad = EnergyVAD(threshold=500.0, silence_ms=60, min_speech_ms=40, sample_rate=16000, frame_ms=20)
    assert vad.process_frame(_frame(0), 16000) is None
    ev = vad.process_frame(_frame(3000), 16000)
    assert ev is not None and ev.kind == "speech_start"
    end = None
    for _ in range(10):
        end = vad.process_frame(_frame(0), 16000)
        if end is not None:
            break
    assert end is not None and end.kind == "speech_end" and len(end.pcm) > 0


def test_vad_ignores_silence() -> None:
    vad = EnergyVAD(threshold=500.0, silence_ms=60, min_speech_ms=40)
    for _ in range(20):
        assert vad.process_frame(_frame(0), 16000) is None
    assert vad.flush() is None


def test_pii_scrub() -> None:
    s = scrub_pii("contattami a mario.rossi@mail.it o al 3331234567, prenota per 2 persone alle 20")
    assert "mario.rossi@mail.it" not in s and "[EMAIL]" in s
    assert "3331234567" not in s
    assert "2 persone" in s  # short numbers preserved


def test_audio_helpers() -> None:
    assert bytes_per_frame(16000, 20) == 640
    assert rms_int16(b"\x00\x00" * 10) == 0.0
    assert split_sentences("Ciao. Come va? Bene!") == ["Ciao.", "Come va?", "Bene!"]
