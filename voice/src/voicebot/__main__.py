"""Uvicorn entrypoint with graceful shutdown."""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

from .config import get_settings
from .logging_json import setup_logging


def _ensure_shared_env() -> bool:
    """Check del venv condiviso via tools/env_setup (best-effort, mai fatale qui)."""
    try:
        root = Path(__file__).resolve().parents[3]  # .../AI_4_Restaurants
        setup_dir = root / "tools" / "env_setup"
        if not setup_dir.is_dir():
            return True  # layout diverso (es. solo voice): nessun check
        sys.path.insert(0, str(setup_dir))
        from env_check import ensure_environment

        return ensure_environment()
    except Exception as exc:  # noqa: BLE001 - il voice non deve morire per il check env
        print(f"[voice] env check saltato: {exc}", flush=True)
        return True


def main() -> None:
    """Run the voice WebSocket server."""
    if not _ensure_shared_env():
        raise SystemExit(3)  # setup eseguito o da completare: riavvia il componente
    settings = get_settings()
    setup_logging(settings.log_level)
    uvicorn.run(
        "voicebot.pipeline.server:app",
        host=settings.voice_host,
        port=settings.voice_port,
        ws="websockets",
        timeout_graceful_shutdown=10,
    )


if __name__ == "__main__":
    main()
