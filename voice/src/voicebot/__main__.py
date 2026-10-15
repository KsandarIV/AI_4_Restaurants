"""``python -m voicebot`` - run the live voice server (uvicorn, graceful shutdown)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

from .config import get_settings
from .logging_json import get_logger, setup_logging


def _ensure_shared_env() -> bool:
    """Best-effort check of the shared venv through ``setup/`` (never fatal here)."""
    if os.environ.get("VOICE_SETUP_SKIP") == "1":
        return True
    try:
        root = Path(__file__).resolve().parents[3]  # .../AI_4_Restaurants
        setup_dir = root / "setup"
        if not setup_dir.is_dir():
            return True  # different layout (e.g. only voice/ was copied, or Docker): no check
        sys.path.insert(0, str(setup_dir))
        from env_check import ensure_environment

        return bool(ensure_environment(role="voice"))
    except Exception as exc:  # noqa: BLE001 - the voice bot must not die because of this check
        print(f"[voice] environment check skipped: {exc}", flush=True)
        return True


def main() -> None:
    """Run the voice WebSocket server."""
    if not _ensure_shared_env():
        raise SystemExit(3)  # setup ran or needs finishing: restart the component
    settings = get_settings()
    setup_logging(settings.log_level)
    log = get_logger("main")
    log.info(
        "voice bot starting port=%d be=%s language=%s stt=%s tts=%s registration=%s",
        settings.voice_port, settings.backend_base_url, settings.voice_language,
        settings.stt_backend, settings.tts_backend, settings.require_registration,
    )
    log.info("tip: `python -m voicebot.doctor` explains any problem with this setup")
    uvicorn.run(
        "voicebot.pipeline.server:create_default_app",
        factory=True,
        host=settings.voice_host,
        port=settings.voice_port,
        ws="auto",
        timeout_graceful_shutdown=10,
        log_config=None,  # keep our JSON logging
    )


if __name__ == "__main__":
    main()
