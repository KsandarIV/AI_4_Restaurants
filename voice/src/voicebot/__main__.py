"""Uvicorn entrypoint with graceful shutdown."""

from __future__ import annotations

import uvicorn

from .config import get_settings
from .logging_json import setup_logging


def main() -> None:
    """Run the voice WebSocket server."""
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
