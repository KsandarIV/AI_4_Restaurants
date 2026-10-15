"""``python -m voicebot.doctor`` - tells you in 5 seconds why the voice bot does not work.

Checks this machine (interpreter, packages, models, audio devices, port) and the BE
(health, LLM, customer registration), and prints a report with a fix for every problem.
Exit code: 0 = all good, 1 = something blocks the voice bot, 2 = only warnings.

    python -m voicebot.doctor                 # uses the .env
    python -m voicebot.doctor --be-url http://10.10.0.5:8000
    python -m voicebot.doctor --json
    python -m voicebot.doctor --load-models   # also load Whisper + Piper (slow, proves they work)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import socket
import sys
import time

from .config import Settings, get_settings
from .diagnostics import Check, _check, collect_diagnostics

_ICON = {"ok": "[ OK ]", "warn": "[WARN]", "fail": "[FAIL]"}


def _port_check(settings: Settings) -> Check:
    """Is the voice port free (or already served by a voice bot)?"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        busy = sock.connect_ex(("127.0.0.1", settings.voice_port)) == 0
    if busy:
        return _check("voice_port", "warn", f"port {settings.voice_port} is already in use",
                      "Another voice bot is running (fine), or change VOICE_PORT.")
    return _check("voice_port", "ok", f"port {settings.voice_port} is free")


def _audio_devices() -> Check:
    try:
        import sounddevice as sd

        default_in, default_out = sd.default.device
        names = sd.query_devices()
        inp = names[default_in]["name"] if default_in is not None and default_in >= 0 else None
        out = names[default_out]["name"] if default_out is not None and default_out >= 0 else None
        if not inp:
            return _check("audio_devices", "warn", "no default microphone", "Plug in / enable a microphone.")
        return _check("audio_devices", "ok", f"mic: {inp} | speaker: {out or 'none'}")
    except Exception as exc:  # noqa: BLE001
        return _check("audio_devices", "warn", f"cannot query audio devices: {exc}")


async def _load_models(settings: Settings) -> list[Check]:
    from .pipeline.server import Models

    models = Models(settings)
    started = time.perf_counter()
    ok = await models.wait(timeout_s=300.0)
    elapsed = time.perf_counter() - started
    if not ok:
        return [_check("model_load", "fail", models.error or "timeout", "See the message above.")]
    return [_check("model_load", "ok", f"STT + TTS loaded in {elapsed:.1f}s, "
                                       f"TTS sample rate {models.tts.sample_rate} Hz")]


async def run(settings: Settings, load_models: bool) -> dict[str, object]:
    """Collect every check into one report."""
    report = await collect_diagnostics(settings)
    checks: list[Check] = list(report["checks"])
    checks.append(_port_check(settings))
    checks.append(_audio_devices())
    if load_models:
        checks.extend(await _load_models(settings))
    report["checks"] = checks
    statuses = {c["status"] for c in checks}
    report["overall"] = "fail" if "fail" in statuses else ("warn" if "warn" in statuses else "ok")
    return report


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(prog="voicebot.doctor", description=__doc__.split("\n")[0])
    parser.add_argument("--be-url", help="override BACKEND_BASE_URL")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--load-models", action="store_true", help="actually load STT and TTS")
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.be_url:
        settings = settings.model_copy(update={"backend_base_url": args.be_url})
    report = asyncio.run(run(settings, args.load_models))

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Voice bot doctor  |  BE: {report['be_url']}  |  language: {report['language']}  "
              f"|  registration: {report['require_registration']}")
        for check in report["checks"]:  # type: ignore[attr-defined]
            print(f"{_ICON[check['status']]} {check['name']:<14} {check['detail']}")
            if check["hint"] and check["status"] != "ok":
                print(f"{'':>22}-> {check['hint']}")
        print(f"\nOverall: {str(report['overall']).upper()}")
    return {"ok": 0, "fail": 1, "warn": 2}[str(report["overall"])]


if __name__ == "__main__":
    sys.exit(main())
