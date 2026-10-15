"""One place that answers "why does it not work?" - shared by ``/diag`` and the doctor CLI.

Each check returns ``{"name", "status": "ok" | "warn" | "fail", "detail", "hint"}``.
``fail`` = the voice bot cannot do its job; ``warn`` = degraded but usable.
Nothing here raises: a broken environment must produce a readable report, not a traceback.
"""

from __future__ import annotations

import importlib
import platform
import sys
from typing import TYPE_CHECKING, Any

import httpx

from .config import Settings, find_env_file, resolve_path

if TYPE_CHECKING:
    from .pipeline.server import Models

Check = dict[str, str]


def _check(name: str, status: str, detail: str, hint: str = "") -> Check:
    return {"name": name, "status": status, "detail": detail, "hint": hint}


def _has(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except Exception:  # noqa: BLE001 - ImportError, but also broken native libs
        return False


def local_checks(settings: Settings) -> list[Check]:
    """Interpreter, .env, packages and model files of THIS machine (no network)."""
    checks: list[Check] = []

    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    checks.append(_check(
        "python", "ok" if in_venv else "warn",
        f"{platform.python_version()} at {sys.executable}",
        "" if in_venv else "Not a virtualenv: use the shared .venv (python setup/setup_env.py).",
    ))

    env_file = find_env_file()
    checks.append(_check(
        "env_file", "ok" if env_file else "warn", env_file or "no .env found, defaults in use",
        "" if env_file else "Run python entrypoint/avvia.py or copy .env.example to .env.",
    ))

    missing = [m for m in ("fastapi", "httpx", "websockets", "numpy", "phonenumbers", "pydantic_settings")
               if not _has(m)]
    checks.append(_check(
        "packages", "fail" if missing else "ok",
        f"missing: {', '.join(missing)}" if missing else "required packages present",
        "pip install -r setup/requirements/base.txt -r setup/requirements/voice.txt" if missing else "",
    ))

    if settings.stt_backend == "faster-whisper":
        ok = _has("faster_whisper")
        checks.append(_check(
            "stt", "ok" if ok else "fail",
            f"faster-whisper model '{settings.stt_model}' ({settings.effective_stt_language})"
            if ok else "faster-whisper not installed",
            "" if ok else "pip install faster-whisper, or set STT_BACKEND=fake for a dry run.",
        ))
    else:
        checks.append(_check("stt", "warn", "STT_BACKEND=fake: speech is NOT recognised",
                             "Set STT_BACKEND=faster-whisper for real use."))

    if settings.tts_backend == "piper":
        model = resolve_path(settings.piper_model_path)
        if not _has("piper"):
            checks.append(_check("tts", "fail", "piper-tts not installed",
                                 "pip install piper-tts, or set TTS_BACKEND=fake for a dry run."))
        elif not model.is_file():
            checks.append(_check(
                "tts", "fail", f"Piper model not found: {settings.piper_model_path}",
                "Run python setup/setup_env.py (downloads voice/models/) or fix PIPER_MODEL_PATH.",
            ))
        elif not model.with_name(model.name + ".json").is_file():
            checks.append(_check("tts", "fail", f"missing {model.name}.json next to the model",
                                 "Download both files of the Piper voice."))
        else:
            checks.append(_check("tts", "ok", f"Piper voice {model.name}"))
    else:
        checks.append(_check("tts", "warn", "TTS_BACKEND=fake: replies are beeps, not speech",
                             "Set TTS_BACKEND=piper for real use."))

    if settings.vad_mode == "webrtc":
        ok = _has("webrtcvad")
        checks.append(_check("vad", "ok" if ok else "fail", "webrtcvad" if ok else "webrtcvad missing",
                             "" if ok else "Use VAD_MODE=energy or install webrtcvad-wheels."))
    else:
        checks.append(_check("vad", "ok", f"energy threshold={settings.vad_energy_threshold:g}"))

    from .anonymizer import ner_available

    checks.append(_check(
        "anonymizer", "ok" if ner_available() else "warn",
        "regex layers + spaCy NER" if ner_available() else "regex layers only (spaCy it_core_news_md missing)",
        "" if ner_available() else "python -m spacy download it_core_news_md  (extra safety net, optional).",
    ))

    audio_ok = _has("sounddevice")
    checks.append(_check(
        "audio_io", "ok" if audio_ok else "warn",
        "sounddevice present (local mic/speaker for v2 and live_client)" if audio_ok
        else "sounddevice missing: only the browser page can capture audio",
        "" if audio_ok else "pip install sounddevice",
    ))
    return checks


async def backend_checks(settings: Settings) -> tuple[dict[str, Any], list[Check]]:
    """Reachability, health, model and customer-registration support of the BE."""
    base = settings.backend_base_url.rstrip("/")
    be: dict[str, Any] = {"ok": False, "detail": "not reached", "model": ""}
    checks: list[Check] = []
    unreachable_hint = (
        f"BE not reachable at {base}: is it running, is BACKEND_BASE_URL the BE machine's LAN IP "
        "(not localhost), and is TCP 8000 open in its firewall?"
    )
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(6.0, connect=3.0)) as client:
            health: httpx.Response | None = None
            for path in ("/api/health", "/health"):
                try:
                    resp = await client.get(base + path)
                except httpx.HTTPError as exc:
                    be["detail"] = f"{type(exc).__name__}: {exc}"
                    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
                        break  # nobody is listening: the other path would fail the same way
                    continue
                if resp.status_code == 200:
                    health, be["detail"] = resp, f"200 on {path}"
                    break
                be["detail"] = f"HTTP {resp.status_code} on {path}"
            if health is None:
                checks.append(_check("backend", "fail", str(be["detail"]), unreachable_hint))
                return be, checks
            try:
                body = health.json()
            except ValueError:
                body = {}
            be["ok"] = True
            be["model"] = str(body.get("llm_model", body.get("model", "")) or "")
            status = str(body.get("status", "online"))
            if status != "online":
                checks.append(_check(
                    "backend", "warn",
                    f"status={status} llm_reachable={body.get('llm_reachable')} "
                    f"model_available={body.get('llm_model_available')}",
                    "BE is up but its LLM is not: start Ollama on the BE machine and check `ollama list`.",
                ))
            else:
                checks.append(_check("backend", "ok", f"online, model {be['model'] or '?'}"))

            # An empty body must be answered 422 (validation) by a BE that supports registration.
            try:
                reg = await client.post(base + "/api/customers", json={})
                if reg.status_code in (404, 405):
                    checks.append(_check("registration", "fail", f"POST /api/customers -> {reg.status_code}",
                                         "BE too old: it needs POST /api/customers (update backend/)."))
                else:
                    checks.append(_check("registration", "ok", f"POST /api/customers answers ({reg.status_code})"))
            except httpx.HTTPError as exc:
                checks.append(_check("registration", "warn", f"{type(exc).__name__}: {exc}"))

            if settings.chat_service_url:
                chat_base = settings.chat_service_url.rstrip("/")
                try:
                    resp = await client.get(chat_base + "/health")
                    checks.append(_check(
                        "chat_service", "ok" if resp.status_code == 200 else "fail",
                        f"{chat_base}/health -> {resp.status_code}",
                        "" if resp.status_code == 200 else "Start chat/api.py (port 8002) on the CHAT machine.",
                    ))
                except httpx.HTTPError as exc:
                    checks.append(_check("chat_service", "fail", f"{type(exc).__name__}: {exc}",
                                         "CHAT_SERVICE_URL is set but the chat service does not answer."))
    except Exception as exc:  # noqa: BLE001
        be["detail"] = f"{type(exc).__name__}: {exc}"
        checks.append(_check("backend", "fail", str(be["detail"]), unreachable_hint))
    return be, checks


async def collect_diagnostics(settings: Settings, models: Models | None = None) -> dict[str, Any]:
    """Full report. Keeps the keys the status panel of the test page already reads."""
    be, be_checks = await backend_checks(settings)
    checks = [*local_checks(settings), *be_checks]
    if models is not None:
        if models.error:
            checks.append(_check("models", "fail", models.error, "See the voice log for the traceback."))
        else:
            checks.append(_check("models", "ok" if models.ready else "warn",
                                 "loaded" if models.ready else "loading in background..."))
    worst = "fail" if any(c["status"] == "fail" for c in checks) else (
        "warn" if any(c["status"] == "warn" for c in checks) else "ok")
    return {
        "voice": "ok",
        "overall": worst,
        "be_url": settings.backend_base_url.rstrip("/"),
        "be": be,
        "language": settings.voice_language,
        "require_registration": settings.require_registration,
        "stt_backend": settings.stt_backend,
        "tts_backend": settings.tts_backend,
        "sample_rate": settings.sample_rate,
        "tts_sample_rate": models.tts.sample_rate if models is not None else settings.tts_sample_rate,
        "checks": checks,
    }
