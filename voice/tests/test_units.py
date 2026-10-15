"""Unit tests with no network and no models: VAD, audio helpers, STT/TTS, config."""

from __future__ import annotations

import io
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.helpers import loud, silence
from voicebot.audio import SentenceChunker, bytes_per_frame, pcm_duration_s, rms_int16, speakable, split_sentences
from voicebot.config import Settings, resolve_path
from voicebot.stt import FakeSTT, build_stt
from voicebot.tts import FakeTTS, PiperTTS, build_tts
from voicebot.vad import EnergyVAD, build_vad

# ---------------- VAD ----------------


def _vad() -> EnergyVAD:
    return EnergyVAD(threshold=500.0, silence_ms=60, min_speech_ms=40, sample_rate=16000, frame_ms=20)


def test_vad_segments_speech() -> None:
    vad = _vad()
    assert vad.process_frame(silence(), 16000) is None
    start = vad.process_frame(loud(), 16000)
    assert start is not None and start.kind == "speech_start"
    vad.process_frame(loud(), 16000)
    end = None
    for _ in range(10):
        end = vad.process_frame(silence(), 16000)
        if end is not None:
            break
    assert end is not None and end.kind == "speech_end" and len(end.pcm) > 0


def test_vad_ignores_silence_and_clicks() -> None:
    vad = _vad()
    for _ in range(20):
        assert vad.process_frame(silence(), 16000) is None
    assert vad.flush() is None
    vad.process_frame(loud(), 16000)  # a single 20 ms click is shorter than min_speech_ms
    events = [vad.process_frame(silence(), 16000) for _ in range(6)]
    assert all(e is None for e in events)


def test_vad_reports_burst_duration() -> None:
    vad = _vad()
    assert vad.speech_ms == 0.0
    for _ in range(5):
        vad.process_frame(loud(), 16000)
    assert vad.speech_ms == 100.0
    vad.reset()
    assert vad.speech_ms == 0.0


@pytest.mark.parametrize("chunk", [320, 2048])  # 20 ms (python client) and 128 ms (browser)
def test_vad_pause_detection_does_not_depend_on_chunk_size(chunk: int) -> None:
    vad = EnergyVAD(threshold=500.0, silence_ms=600, min_speech_ms=250)
    for _ in range(int(1000 / (chunk / 16))):  # one second of speech
        vad.process_frame(loud(chunk), 16000)
    waited_ms, end = 0.0, None
    while end is None:
        end = vad.process_frame(silence(chunk), 16000)
        waited_ms += chunk / 16
    assert 600 <= waited_ms < 600 + chunk / 16 + 1


def test_build_vad_modes() -> None:
    assert isinstance(build_vad("energy", threshold=300.0), EnergyVAD)
    webrtc = build_vad("webrtc", threshold=300.0, frame_ms=20)  # threshold must be ignored
    assert webrtc.speech_ms == 0.0


# ---------------- audio helpers ----------------


def test_audio_helpers() -> None:
    assert bytes_per_frame(16000, 20) == 640
    assert rms_int16(b"\x00\x00" * 10) == 0.0
    assert rms_int16(b"") == 0.0
    assert pcm_duration_s(b"\x00\x00" * 16000, 16000) == 1.0
    assert split_sentences("Ciao. Come va? Bene!") == ["Ciao.", "Come va?", "Bene!"]


def test_sentence_chunker_streams_whole_sentences() -> None:
    chunker = SentenceChunker(min_chars=5)
    out: list[str] = []
    for token in ["Certo, ", "ho capito. ", "A che ", "ora?"]:
        out += chunker.feed(token)
    assert out == ["Certo, ho capito.", "A che ora?"]
    assert chunker.flush() == []


def test_sentence_chunker_merges_tiny_sentences_and_flushes_tail() -> None:
    chunker = SentenceChunker(min_chars=12)
    assert chunker.feed("Ok. ") == []  # too short to be its own utterance
    assert chunker.feed("Tavolo per due ") == []
    assert chunker.flush() == ["Ok. Tavolo per due"]


def test_speakable_cleans_markdown_and_spells_codes() -> None:
    assert speakable("**Ciao** #1 | ok 🍝") == "Ciao 1 ok"
    assert speakable("Il codice è RES-9A8B2C.") == "Il codice è R E S, 9 A 8 B 2 C."


# ---------------- STT / TTS ----------------


async def test_fake_stt_script_and_silence() -> None:
    stt = FakeSTT(script=["uno", "due"])
    assert await stt.transcribe(loud(), 16000) == "uno"
    assert await stt.transcribe(silence(), 16000) == ""  # silence never consumes the script
    assert await stt.transcribe(loud(), 16000) == "due"
    assert await stt.transcribe(loud(), 16000) == "due"  # last entry repeats
    assert isinstance(build_stt("fake"), FakeSTT)


class _FakeWhisperModel:
    """Stands in for faster_whisper.WhisperModel: records the call, returns canned segments."""

    def __init__(self, text: str, no_speech_prob: float = 0.0) -> None:
        self.text, self.no_speech_prob, self.kwargs = text, no_speech_prob, {}

    def transcribe(self, audio: object, **kwargs: object):  # type: ignore[no-untyped-def]
        self.kwargs = kwargs
        return [SimpleNamespace(text=self.text, no_speech_prob=self.no_speech_prob)], None


async def test_whisper_gets_the_booking_prompt_and_drops_hallucinations() -> None:
    from voicebot.stt import FasterWhisperSTT

    stt = FasterWhisperSTT(language="it", initial_prompt="Prenotazione di un tavolo al ristorante. Nome.")
    model = _FakeWhisperModel("Mario Rossi 333 1234567")
    stt._model = model
    assert await stt.transcribe(loud(3200), 16000) == "Mario Rossi 333 1234567"
    assert model.kwargs["initial_prompt"].startswith("Prenotazione") and model.kwargs["language"] == "it"
    stt._model = _FakeWhisperModel("Prenotazione di un tavolo al ristorante. Nome e cognome")  # prompt echoed from noise
    assert await stt.transcribe(loud(3200), 16000) == ""
    stt._model = _FakeWhisperModel("Sottotitoli a cura di qualcuno")
    assert await stt.transcribe(loud(3200), 16000) == ""
    stt._model = _FakeWhisperModel("rumore", no_speech_prob=0.9)
    assert await stt.transcribe(loud(3200), 16000) == ""
    assert await stt.transcribe(bytes(20), 16000) == ""  # < 100 ms is never sent to the model


def test_whisper_prompt_is_off_unless_configured() -> None:
    assert Settings().effective_stt_prompt == ""
    assert Settings(stt_initial_prompt="custom").effective_stt_prompt == "custom"
    assert Settings().stt_model == "small"


async def test_fake_tts_streams_one_chunk_per_sentence() -> None:
    tts = FakeTTS()

    async def tokens():  # type: ignore[no-untyped-def]
        for t in ["Buongiorno a tutti. ", "Come posso ", "aiutarla?"]:
            yield t

    chunks = [c async for c in tts.synthesize_stream(tokens())]
    assert len(chunks) == 2
    assert tts.spoken == ["Buongiorno a tutti.", "Come posso aiutarla?"]
    assert isinstance(build_tts("fake"), FakeTTS)


class _NewPiperVoice:
    """piper-tts >= 1.3: ``synthesize`` yields AudioChunk objects."""

    config = SimpleNamespace(sample_rate=16000)

    def synthesize_wav(self) -> None:  # presence marks the new API
        raise AssertionError("not used")

    def synthesize(self, text: str):  # type: ignore[no-untyped-def]
        yield SimpleNamespace(audio_int16_bytes=b"\x01\x00" * 100)
        yield SimpleNamespace(audio_int16_bytes=b"\x02\x00" * 50)


class _OldPiperVoice:
    """piper-tts <= 1.2: ``synthesize(text, wav_file)``."""

    config = SimpleNamespace(sample_rate=22050)

    def synthesize(self, text: str, wav_file: wave.Wave_write) -> None:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(b"\x03\x00" * 80)


@pytest.mark.parametrize(("voice", "expected_bytes"), [(_NewPiperVoice(), 300), (_OldPiperVoice(), 160)])
def test_piper_supports_old_and_new_api(voice: object, expected_bytes: int) -> None:
    tts = PiperTTS(model_path="unused.onnx")
    tts._voice = voice
    assert len(tts._synth("Ciao")) == expected_bytes


def test_piper_missing_model_gives_actionable_error() -> None:
    tts = PiperTTS(model_path="models/does-not-exist.onnx")
    with pytest.raises((FileNotFoundError, ImportError)) as info:
        tts._ensure_voice()
    assert "does-not-exist" in str(info.value) or "piper" in str(info.value).lower()


# ---------------- config ----------------


def test_resolve_path_finds_models_from_any_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)  # a cwd that is neither the repo root nor voice/
    resolved = resolve_path("voice/models/it_IT-riccardo-x_low.onnx")
    repo_model = Path(__file__).resolve().parents[2] / "voice" / "models" / "it_IT-riccardo-x_low.onnx"
    if repo_model.is_file():
        assert resolved == repo_model
    absolute = tmp_path / "x.onnx"
    assert resolve_path(str(absolute)) == absolute


def test_settings_defaults_are_local_and_follow_language() -> None:
    settings = Settings()
    assert settings.backend_base_url.startswith("http://127.0.0.1") or "localhost" in settings.backend_base_url
    assert settings.effective_stt_language == settings.voice_language
    assert Settings(stt_language="en").effective_stt_language == "en"


def test_wav_roundtrip_helper() -> None:
    from voicebot.audio import pcm_to_wav

    with wave.open(io.BytesIO(pcm_to_wav(b"\x00\x00" * 160, 16000)), "rb") as wf:
        assert wf.getframerate() == 16000 and wf.getnframes() == 160
