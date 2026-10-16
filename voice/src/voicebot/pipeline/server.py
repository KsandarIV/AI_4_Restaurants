"""FastAPI server: WebSocket PCM16 in -> PCM16 out + JSON control messages.

Protocol (binary frames = mono PCM16LE at ``settings.sample_rate``):
  client -> server: audio bytes | {"cmd": "eos"} | {"cmd": "reset"}
  server -> client: audio bytes (TTS, at the ``tts_sample_rate`` of the ready event) |
                    {"event": "ready" | "loading" | "heard" | "transcript" | "thinking" |
                               "reply" | "barge_in" | "error", ...}

STT and TTS are loaded ONCE (in the background at startup) and shared by every call:
loading a model per connection would add seconds of latency and gigabytes of RAM.
Reconnection: a connection is stateless, so the client simply reconnects with
exponential backoff (``voicebot.live_client`` and the test page both do).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from ..backend import BackendClient, BackendError
from ..config import Settings, get_settings
from ..diagnostics import collect_diagnostics
from ..interfaces import AbstractLLMOrchestrator, AbstractSTT, AbstractTTS
from ..logging_json import get_logger, setup_logging
from ..orchestrator import ANON_CUSTOMER_ID, BackendOrchestrator
from ..peers_file import chat_service_url
from ..stt import build_stt
from ..tts import build_tts
from ..vad import build_vad
from .session import VoiceSession

log = get_logger("server")
_PAGES = Path(__file__).parent


class Models:
    """The STT and TTS models, shared by all sessions and loaded once in the background."""

    def __init__(self, settings: Settings) -> None:
        self.stt: AbstractSTT = build_stt(
            settings.stt_backend,
            model=settings.stt_model,
            device=settings.stt_device,
            compute_type=settings.stt_compute_type,
            language=settings.effective_stt_language,
            initial_prompt=settings.effective_stt_prompt,
        )
        self.tts: AbstractTTS = build_tts(
            settings.tts_backend,
            model_path=settings.piper_model_path,
            config_path=settings.piper_config_path,
            sample_rate=settings.tts_sample_rate,
        )
        self.ready = False
        self.error = ""
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Begin loading in the background (idempotent)."""
        if self._task is None:
            self._task = asyncio.ensure_future(self._load())

    async def _load(self) -> None:
        try:
            await self.stt.warmup()
            await self.tts.warmup()
            self.ready = True
            log.info("models ready tts_sample_rate=%d", self.tts.sample_rate)
        except Exception as exc:  # noqa: BLE001 - reported through /ready, /diag and the WS
            self.error = f"{type(exc).__name__}: {exc}"
            log.error("model loading failed: %s", self.error)

    async def wait(self, timeout_s: float = 120.0) -> bool:
        """Wait until the models are loaded; False on failure or timeout."""
        self.start()
        assert self._task is not None
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(self._task), timeout=timeout_s)
        return self.ready

    async def close(self) -> None:
        """Release both models."""
        for closer in (self.stt.aclose, self.tts.aclose):
            with contextlib.suppress(Exception):
                await asyncio.wait_for(closer(), timeout=5.0)


async def warm_backend(settings: Settings) -> None:
    """One throw-away BE turn so the LLM has already read its prompt when the first caller speaks."""
    backend = BackendClient(
        base_url=settings.backend_base_url,
        timeout_s=settings.backend_timeout_s,
        api_key=settings.backend_api_key,
        chat_timeout_s=max(settings.backend_chat_timeout_s, 300.0),
    )
    try:
        await backend.chat("Buongiorno", "voice_warmup", ANON_CUSTOMER_ID)
        log.info("backend warmed up")
    except BackendError as exc:
        log.info("backend warm-up skipped kind=%s status=%s", exc.kind, exc.status)
    finally:
        await backend.aclose()


def make_orchestrator(settings: Settings) -> AbstractLLMOrchestrator:
    """The chat bot's conversation, bound to this caller (one BE client per call)."""
    backend = BackendClient(
        base_url=settings.backend_base_url,
        timeout_s=settings.backend_timeout_s,
        api_key=settings.backend_api_key,
        chat_stream_path=settings.backend_chat_stream_path,
        chat_timeout_s=settings.backend_chat_timeout_s,
    )
    return BackendOrchestrator(
        backend=backend,
        system_prompt=settings.llm_system_prompt,
        max_history=settings.llm_max_history,
        language=settings.voice_language,
        require_registration=settings.require_registration,
        max_exchanges=settings.context_max_exchanges,
        max_resets=settings.context_max_resets,
    )


def make_session(
    settings: Settings,
    models: Models,
    on_control: Any = None,
    llm: AbstractLLMOrchestrator | None = None,
) -> VoiceSession:
    """Assemble one call: private VAD + conversation, shared STT/TTS."""
    return VoiceSession(
        vad=build_vad(
            settings.vad_mode,
            threshold=settings.vad_energy_threshold,
            silence_ms=settings.vad_silence_ms,
            min_speech_ms=settings.vad_min_speech_ms,
            max_segment_s=settings.vad_max_segment_s,
            sample_rate=settings.sample_rate,
            frame_ms=settings.frame_ms,
        ),
        stt=models.stt,
        llm=llm or make_orchestrator(settings),
        tts=models.tts,
        sample_rate=settings.sample_rate,
        audio_in_max=settings.audio_in_queue_max,
        text_max=settings.text_queue_max,
        audio_out_max=settings.audio_out_queue_max,
        barge_in_enabled=settings.barge_in_enabled,
        barge_in_min_ms=settings.barge_in_min_ms,
        stt_timeout_s=settings.stt_timeout_s,
        on_control=on_control,
        owns_models=False,
    )


def _page(name: str, test: bool = False, be_url: str = "") -> str:
    html = (_PAGES / name).read_text(encoding="utf-8")
    if "{{TITLE_SUFFIX}}" not in html:
        return html
    if test:
        banner = (
            '<div style="background:#3a1f14;color:#fff;text-align:center;padding:8px;'
            'font-family:system-ui,sans-serif;font-size:.85rem;letter-spacing:.08em">'
            f"VOICE / TESTS — ambiente di test · BE in uso: {be_url}</div>"
        )
        return html.replace("{{TITLE_SUFFIX}}", " / TESTS").replace("{{TEST_BANNER}}", banner)
    return html.replace("{{TITLE_SUFFIX}}", "").replace("{{TEST_BANNER}}", "")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the FastAPI app with injected settings (test-friendly)."""
    settings = settings or get_settings()
    setup_logging(settings.log_level)
    models = Models(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if settings.preload_models:
            models.start()  # background: /health answers immediately, /ready flips when loaded
            if settings.warm_backend:
                warm_task = asyncio.ensure_future(warm_backend(settings))
        try:
            yield
        finally:
            if settings.preload_models and settings.warm_backend:
                warm_task.cancel()
            await models.close()

    app = FastAPI(title="Voice bot - Trattoria Bella Napoli", lifespan=lifespan)
    # The complete site (showcase/) is served from another origin and calls /site/* here: LAN demo, so open.
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.models = models
    app.state.settings = settings

    # ---------------- health & diagnostics ----------------

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> Response:
        report = await collect_diagnostics(settings, models)
        ok = bool(report["be"]["ok"]) and models.ready
        body = {
            "status": "ready" if ok else "degraded",
            "backend": report["be_url"],
            "models_ready": models.ready,
            "models_error": models.error,
        }
        return JSONResponse(body, status_code=200 if ok else 503)

    @app.get("/diag")
    async def diag() -> dict[str, Any]:
        """Live diagnosis for the status panel: voice + BE + models + every local check."""
        return await collect_diagnostics(settings, models)

    # ---------------- pages ----------------

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def site() -> str:
        """The restaurant site with the voice assistant and "My reservations"."""
        return (_PAGES / "site" / "index.html").read_text(encoding="utf-8")

    app.mount("/site-assets", StaticFiles(directory=_PAGES / "site"), name="site-assets")

    # The site never talks to the BE directly: menu, info and reservation lookups go through here.
    async def _be_get(path: str, params: dict[str, str] | None = None) -> Response:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=3.0)) as client:
                resp = await client.get(settings.backend_base_url.rstrip("/") + path, params=params)
        except httpx.HTTPError:
            return JSONResponse({"detail": "BE not reachable"}, status_code=502)
        return Response(resp.content, status_code=resp.status_code, media_type="application/json")

    @app.get("/site/config", include_in_schema=False)
    async def site_config() -> dict[str, Any]:
        return {"language": settings.voice_language, "mode": settings.mode,
                "require_registration": settings.require_registration}

    @app.get("/site/menu", include_in_schema=False)
    async def site_menu() -> Response:
        return await _be_get("/api/menu")

    @app.get("/site/info", include_in_schema=False)
    async def site_info() -> Response:
        return await _be_get("/api/info")

    @app.get("/site/reservation/{code}", include_in_schema=False)
    async def site_reservation(code: str, customer_id: str = "") -> Response:
        """One reservation of the caller (the BE answers 404 for anybody else's: codes are not guessable)."""
        if not re.fullmatch(r"[A-Za-z0-9-]{4,20}", code) or not customer_id:
            return JSONResponse({"detail": "invalid request"}, status_code=400)
        return await _be_get(f"/api/reservations/{code.upper()}", {"customer_id": customer_id})

    @app.get("/test-voice", response_class=HTMLResponse, include_in_schema=False)
    async def test_voice_page() -> str:
        """The live test page: always carries the banner that shows which BE this instance talks to."""
        return _page("voice_test.html", True, settings.backend_base_url)

    for old_route in ("/prova-vocale", "/prova-vocale-test"):  # the old addresses keep working
        app.add_api_route(
            old_route, (lambda: RedirectResponse("/test-voice")), methods=["GET"], include_in_schema=False,
        )

    async def _chat_proxy(path: str, body: dict[str, Any]) -> Response:
        """The site's chat window: forwards to the CHAT service (chat/api.py) when CHAT_SERVICE_URL is set."""
        chat_base = chat_service_url(settings.chat_service_url)  # configured, else the verified CHAT peer
        if not chat_base:
            return JSONResponse({"detail": "Il servizio chat non è collegato a questo server."}, status_code=503)
        try:
            async with httpx.AsyncClient(timeout=130.0) as client:
                resp = await client.post(chat_base + path, json=body)
        except httpx.HTTPError:
            return JSONResponse({"detail": "Non riesco a contattare il servizio chat."}, status_code=502)
        try:
            data = resp.json()
        except ValueError:
            data = {"detail": "Risposta non valida dal servizio chat."}
        return JSONResponse(data, status_code=resp.status_code)

    @app.post("/site/chat/session", include_in_schema=False)
    async def site_chat_session() -> Response:
        return await _chat_proxy("/chat/session", {})

    @app.post("/site/chat/message", include_in_schema=False)
    async def site_chat_message(payload: dict[str, Any]) -> Response:
        session_id, text = str(payload.get("session_id", ""))[:80], str(payload.get("text", ""))[:2000]
        if not session_id or not text.strip():
            return JSONResponse({"detail": "invalid request"}, status_code=400)
        return await _chat_proxy("/chat/message", {"session_id": session_id, "text": text})

    for route, name in (("/tech", "tech.html"), ("/tech-codice", "tech_codice.html"),
                        ("/tech-idea", "tech_idea.html")):
        app.add_api_route(
            route, (lambda n=name: HTMLResponse(_page(n))), methods=["GET"],
            include_in_schema=False,
        )

    # ---------------- the call ----------------

    @app.websocket("/ws/voice")
    async def ws_voice(ws: WebSocket) -> None:
        await ws.accept()
        if not models.ready:
            await _send(ws, {"event": "loading"})
            if not await models.wait():
                await _send(ws, {"event": "error", "detail": "models_failed", "message": models.error})
                await ws.close()
                return

        async def on_control(payload: dict[str, str]) -> None:
            await _send(ws, payload)

        session = make_session(settings, models, on_control=on_control)
        log.info("ws open session=%s", session.session_id)
        await _send(ws, {
            "event": "ready",
            "session_id": session.session_id,
            "sample_rate": settings.sample_rate,
            "tts_sample_rate": models.tts.sample_rate,
        })
        run_task = asyncio.create_task(session.run())
        writer = asyncio.create_task(_writer(ws, session))
        try:
            await _reader(ws, session, settings)
        except WebSocketDisconnect:
            log.info("ws disconnect session=%s", session.session_id)
        except Exception as exc:  # noqa: BLE001
            log.error("ws error session=%s err=%r", session.session_id, exc)
        finally:
            writer.cancel()
            await session.close()
            run_task.cancel()
            for task in (writer, run_task):
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            with contextlib.suppress(Exception):
                await ws.close()

    return app


async def _send(ws: WebSocket, payload: dict[str, Any]) -> None:
    """Send a control message; a closed socket is not an error."""
    with contextlib.suppress(Exception):
        await ws.send_text(json.dumps(payload, ensure_ascii=False))


async def _writer(ws: WebSocket, session: VoiceSession) -> None:
    """Drain ``audio_out_q`` into the WebSocket."""
    try:
        while True:
            chunk = await session.next_output()
            if chunk is None:
                return
            await ws.send_bytes(chunk)
    except (WebSocketDisconnect, asyncio.CancelledError):
        raise
    except Exception as exc:  # noqa: BLE001
        log.error("writer error session=%s err=%r", session.session_id, exc)


async def _reader(ws: WebSocket, session: VoiceSession, settings: Settings) -> None:
    """Read audio frames and commands until the client leaves or goes idle."""
    while True:
        try:
            msg = await asyncio.wait_for(ws.receive(), timeout=settings.ws_idle_timeout_s)
        except asyncio.TimeoutError:
            log.info("ws idle timeout session=%s", session.session_id)
            return
        if msg.get("type") == "websocket.disconnect":
            return
        if msg.get("bytes") is not None:
            await session.push_audio(bytes(msg["bytes"]))
        elif msg.get("text") is not None:
            try:
                command = json.loads(str(msg["text"]))
            except ValueError:
                continue
            if command.get("cmd") == "eos":
                await session.push_audio(None)
                return
            if command.get("cmd") == "reset":
                await session.reset_conversation()


def create_default_app() -> FastAPI:
    """Uvicorn factory entry (``uvicorn voicebot.pipeline.server:create_default_app --factory``)."""
    return create_app()
