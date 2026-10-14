"""Centralised configuration via environment (pydantic-settings).

Tutti i modelli girano in locale; il BE e' raggiunto solo via LAN.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from env / .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    voice_host: str = Field(default="0.0.0.0")
    voice_port: int = Field(default=8003)
    backend_base_url: str = Field(default="http://192.168.1.10:8001")
    backend_timeout_s: float = Field(default=15.0)
    backend_api_key: str = Field(default="")
    backend_chat_stream_path: str = Field(default="/api/chat/stream")
    backend_health_path: str = Field(default="/health")

    sample_rate: int = Field(default=16000)
    frame_ms: int = Field(default=20)
    input_ws_path: str = Field(default="/ws/voice")

    vad_mode: str = Field(default="energy")
    vad_energy_threshold: float = Field(default=500.0)
    vad_silence_ms: int = Field(default=600)
    vad_min_speech_ms: int = Field(default=250)
    vad_max_segment_s: float = Field(default=15.0)

    stt_backend: str = Field(default="faster-whisper")
    stt_model: str = Field(default="tiny")
    stt_device: str = Field(default="cpu")
    stt_compute_type: str = Field(default="int8")
    stt_language: str = Field(default="it")

    llm_system_prompt: str = Field(
        default="Sei un assistente vocale di un ristorante. "
        "Rispondi in italiano, conciso, max 2 frasi per turno."
    )
    llm_max_history: int = Field(default=12)
    llm_token_timeout_s: float = Field(default=30.0)

    tts_backend: str = Field(default="piper")
    piper_model_path: str = Field(default="models/it_IT-riccardo-x_low.onnx")
    piper_config_path: str = Field(default="")
    tts_sample_rate: int = Field(default=22050)

    audio_in_queue_max: int = Field(default=200)
    text_queue_max: int = Field(default=32)
    audio_out_queue_max: int = Field(default=200)
    barge_in_enabled: bool = Field(default=True)
    log_level: str = Field(default="INFO")


def get_settings() -> Settings:
    """Return a fresh Settings instance (cheap, reads env)."""
    return Settings()
