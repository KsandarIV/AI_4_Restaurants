"""Shared pytest setup: hermetic tests, clear errors, no dependency on the dev's .env."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

_REQUIRED = ("fastapi", "httpx", "pydantic_settings", "numpy", "phonenumbers", "websockets")


def pytest_configure(config: pytest.Config) -> None:
    """Fail fast with an actionable message when the interpreter lacks dependencies.

    The usual cause is VS Code / a terminal using the *system* Python instead of the
    shared ``.venv`` created by ``setup/setup_env.py``.
    """
    import importlib
    import sys

    missing = []
    for name in _REQUIRED:
        try:
            importlib.import_module(name)
        except ImportError:
            missing.append(name)
    if missing:
        raise pytest.UsageError(
            f"Missing packages for {sys.executable}: {', '.join(missing)}.\n"
            "Use the shared virtualenv:  ..\\.venv\\Scripts\\python -m pytest tests -q  "
            "(or run voice\\test.bat), or select .venv as the interpreter in VS Code."
        )


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Ignore the machine's .env and real models: tests must behave the same everywhere."""
    monkeypatch.chdir(tmp_path)  # no ./.env in cwd
    for key, value in {
        "BACKEND_BASE_URL": "http://127.0.0.1:9",
        "STT_BACKEND": "fake",
        "TTS_BACKEND": "fake",
        "VOICE_LANGUAGE": "it",
        "REQUIRE_REGISTRATION": "true",
        "CHAT_SERVICE_URL": "",
        "LLM_SYSTEM_PROMPT": "",
        "VOICE_SETUP_SKIP": "1",
    }.items():
        monkeypatch.setenv(key, value)
    # The shared root .env still exists on disk: make every Settings() ignore it.
    monkeypatch.setattr("voicebot.config.find_env_file", lambda: None)
    yield
