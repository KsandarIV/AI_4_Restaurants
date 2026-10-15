"""Centralised configuration via environment variables (pydantic-settings).

Every model runs locally; the BE is only reached over the LAN.
Real environment variables always win over the ``.env`` file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]  # .../AI_4_Restaurants
VOICE_DIR = Path(__file__).resolve().parents[2]  # .../AI_4_Restaurants/voice


def find_env_file() -> str | None:
    """Locate the single project ``.env``: cwd -> cwd/voice -> repo root -> voice/.

    Launching from the repo root uses ``<root>/.env``; launching from ``voice/``
    keeps working without changes.
    """
    here = Path.cwd()
    candidates = [
        here / ".env",
        here / "voice" / ".env",
        REPO_ROOT / ".env",
        VOICE_DIR / ".env",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def resolve_path(raw: str) -> Path:
    """Resolve a (possibly relative) file path against cwd, repo root and ``voice/``.

    ``PIPER_MODEL_PATH=voice/models/x.onnx`` must work whether the process was
    started from the repo root, from ``voice/`` or from an IDE with another cwd.
    Returns the first existing candidate, or the path as given when none exists.
    """
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    for base in (Path.cwd(), REPO_ROOT, VOICE_DIR, VOICE_DIR.parent):
        candidate = (base / path).resolve()
        if candidate.exists():
            return candidate
    return path


class Settings(BaseSettings):
    """Application settings loaded from env / .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Server ---
    mode: Literal["real", "local"] = Field(default="real")  # "local" = stub BE (voicebot local)
    voice_host: str = Field(default="0.0.0.0")
    voice_port: int = Field(default=8003)
    ws_idle_timeout_s: float = Field(default=60.0)

    # --- Backend (separate LAN machine) ---
    backend_base_url: str = Field(default="http://localhost:8000")
    backend_timeout_s: float = Field(default=15.0)
    backend_chat_timeout_s: float = Field(default=120.0)  # local LLM can be slow
    backend_api_key: str = Field(default="")
    backend_chat_stream_path: str = Field(default="/api/chat/stream")
    backend_health_path: str = Field(default="/health")

    # --- Conversation (must mirror the chat bot) ---
    voice_language: Literal["it", "en"] = Field(default="it")
    # Same switch the BE has: registration (name + phone) before any booking.
    require_registration: bool = Field(default=True)
    # v2 only: when set, drive the CHAT service (chat/api.py, e.g. http://host:8002)
    # instead of talking to the BE directly. Off by default: the brief says the
    # bots talk to the BE only.
    chat_service_url: str = Field(default="")
    # Empty = use the built-in English agent prompt (voicebot.prompts).
    llm_system_prompt: str = Field(default="")
    llm_max_history: int = Field(default=12)
    llm_token_timeout_s: float = Field(default=120.0)

    # --- Audio ---
    sample_rate: int = Field(default=16000)
    frame_ms: int = Field(default=20)
    input_ws_path: str = Field(default="/ws/voice")

    # --- VAD ---
    vad_mode: Literal["energy", "webrtc"] = Field(default="energy")
    vad_energy_threshold: float = Field(default=500.0)
    vad_silence_ms: int = Field(default=600)
    vad_min_speech_ms: int = Field(default=250)
    vad_max_segment_s: float = Field(default=15.0)

    # --- STT ---
    stt_backend: Literal["faster-whisper", "fake"] = Field(default="faster-whisper")
    # "tiny" mangles digits and names (measured); "small" is accurate at ~1.5 s per 4 s of speech on CPU.
    stt_model: str = Field(default="small")
    stt_device: str = Field(default="cpu")
    stt_compute_type: str = Field(default="int8")
    stt_language: str = Field(default="")  # empty = follow VOICE_LANGUAGE
    stt_timeout_s: float = Field(default=30.0)
    # Optional context text for Whisper (vocabulary hints). Empty = none: prompts can be echoed back.
    stt_initial_prompt: str = Field(default="")

    # --- TTS ---
    tts_backend: Literal["piper", "fake"] = Field(default="piper")
    piper_model_path: str = Field(default="voice/models/it_IT-riccardo-x_low.onnx")
    piper_config_path: str = Field(default="")
    tts_sample_rate: int = Field(default=22050)

    # --- Pipeline ---
    audio_in_queue_max: int = Field(default=200)
    text_queue_max: int = Field(default=32)
    audio_out_queue_max: int = Field(default=200)
    barge_in_enabled: bool = Field(default=True)
    # Speech must last this long while the bot talks before it counts as an
    # interruption (filters clicks, coughs and speaker echo).
    barge_in_min_ms: int = Field(default=300)
    preload_models: bool = Field(default=True)  # load STT/TTS at startup, not at first call
    log_level: str = Field(default="INFO")

    @property
    def effective_stt_prompt(self) -> str:
        """Whisper initial prompt: only what STT_INITIAL_PROMPT says. Off by default - measured:
        a prompt with a sample name/number made Whisper-small answer with the prompt itself."""
        return self.stt_initial_prompt

    @property
    def effective_stt_language(self) -> str:
        """Whisper language code: explicit STT_LANGUAGE, else the conversation language."""
        return self.stt_language or self.voice_language


def get_settings() -> Settings:
    """Return a fresh Settings instance (cheap: reads env + the shared root .env)."""
    env_file = find_env_file()
    if env_file is not None:
        return Settings(_env_file=env_file)  # type: ignore[call-arg]
    return Settings()
