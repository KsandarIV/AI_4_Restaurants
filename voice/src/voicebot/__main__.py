"""``python -m voicebot [command]`` - one entry point for everything.

    python -m voicebot                run the live server (what avvia.py starts on the VOICE machine)
    python -m voicebot real           same, after checking the BE (waits for it to come up)
    python -m voicebot local          LOCAL TEST of v1 live: stub BE + voice server + test page, nothing else needed
    python -m voicebot doctor         why does it not work? (checks this machine and the BE)
    python -m voicebot v2 [--text]    on-demand voice chat from this PC
    python -m voicebot live [url]     live call from this PC (no browser)

On Windows ``voice\\voice.bat <command>`` does the same with the shared .venv.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
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


def serve() -> None:
    """Run the voice WebSocket server (uvicorn, graceful shutdown)."""
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
    log.info("test page: http://localhost:%d/test-voice  |  site: http://localhost:%d/  |  `python -m voicebot doctor` explains any problem",
             settings.voice_port, settings.voice_port)
    uvicorn.run(
        "voicebot.pipeline.server:create_default_app",
        factory=True,
        host=settings.voice_host,
        port=settings.voice_port,
        ws="auto",
        timeout_graceful_shutdown=10,
        log_config=None,  # keep our JSON logging
    )


def real(wait_s: float) -> None:
    """The real flow: check the BE first (wait for it, like avvia.py's gate), then serve."""
    from .diagnostics import backend_checks

    settings = get_settings()
    print(f"[voice] REAL mode - BE: {settings.backend_base_url}")
    deadline = time.monotonic() + wait_s
    while True:
        be, checks = asyncio.run(backend_checks(settings))
        if be["ok"] or time.monotonic() >= deadline:
            break
        print(f"[voice] BE not answering yet ({be['detail']}); retrying...", flush=True)
        time.sleep(3.0)
    for check in checks:
        print(f"[voice] {check['status'].upper():<4} {check['name']}: {check['detail']}")
        if check["hint"] and check["status"] != "ok":
            print(f"[voice]      -> {check['hint']}")
    print(f"[voice] test page: http://localhost:{settings.voice_port}/test-voice   site: http://localhost:{settings.voice_port}/")
    if not be["ok"]:
        print("[voice] The BE is not reachable: starting anyway, calls will say so. "
              "Fix BACKEND_BASE_URL / start the BE, then `python -m voicebot doctor`.")
    serve()


def main(argv: list[str] | None = None) -> int:
    """Dispatch the sub-commands."""
    args_in = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(prog="voicebot", description=__doc__.split("\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="run the live server (default)")
    real_p = sub.add_parser("real", help="check the BE, then run the live server")
    real_p.add_argument("--wait", type=float, default=60.0, help="seconds to wait for the BE (default 60)")
    local_p = sub.add_parser("local", help="local test: stub BE + voice server + browser")
    local_p.add_argument("--fake", action="store_true", help="fake STT/TTS: no models, no speech (UI test)")
    local_p.add_argument("--port", type=int, default=0, help="voice port (default: first free from 8003)")
    local_p.add_argument("--no-browser", action="store_true", help="do not open the browser")
    for name, text in (("doctor", "check this machine and the BE"), ("v2", "on-demand voice chat"),
                       ("live", "live call from this PC")):
        sub.add_parser(name, help=text, add_help=False)

    if args_in and args_in[0] in ("doctor", "v2", "live"):  # these parse their own options
        command, rest = args_in[0], args_in[1:]
        if command == "doctor":
            from .doctor import main as doctor_main

            return doctor_main(rest)
        if command == "v2":
            from .v2 import main as v2_main

            return v2_main(rest)
        from .live_client import main as live_main

        return live_main(rest)

    args = parser.parse_args(args_in)
    if args.command in (None, "serve"):
        serve()
    elif args.command == "real":
        real(args.wait)
    elif args.command == "local":
        from .local import run_local

        return run_local(fake=args.fake, port=args.port, open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
