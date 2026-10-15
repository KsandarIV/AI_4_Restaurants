"""FastAPI WebSocket server: PCM16 in -> PCM16 out + JSON control messages.

Protocol (binary frames = mono PCM16LE @ settings.sample_rate):
  client -> server: audio bytes | {"cmd": "eos"} | {"cmd": "reset"}
  server -> client: audio bytes | {"event": "barge_in"} | {"event": "ready", ...}

Re-connection: the endpoint is stateless per connection; the client reconnects
with exponential backoff (see static client example in README). Server side
applies per-read timeouts and always closes the VoiceSession gracefully.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from ..backend import BackendClient
from ..config import Settings, get_settings
from ..logging_json import get_logger, setup_logging
from ..orchestrator import BackendOrchestrator
from ..stt import build_stt
from ..tts import build_tts
from ..vad import build_vad
from .session import VoiceSession

log = get_logger("server")


def _voice_page(path: object, test: bool, be_url: str) -> str:
    """Rende voice_test.html: titolo VOICE o VOICE/TESTS + banner col BE usato."""
    from pathlib import Path

    assert isinstance(path, Path)
    html = path.read_text(encoding="utf-8")
    if test:
        banner = (
            '<div style="background:#3a1f14;color:#fff;text-align:center;padding:8px;'
            'font-family:system-ui,sans-serif;font-size:.85rem;letter-spacing:.08em">'
            f"VOICE / TESTS — ambiente di test · BE in uso: {be_url}</div>"
        )
        return html.replace("{{TITLE_SUFFIX}}", " / TESTS").replace("{{TEST_BANNER}}", banner)
    return html.replace("{{TITLE_SUFFIX}}", "").replace("{{TEST_BANNER}}", "")


def build_app(settings: Settings | None = None) -> FastAPI:
    """Create the FastAPI app with injected settings (test-friendly)."""
    settings = settings or get_settings()
    setup_logging(settings.log_level)
    app = FastAPI(title="Voice-bot Ristorante (Traccia 3)")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    async def root() -> object:
        """La root redirige alla pagina di test (niente 404 a chi apre l'IP)."""
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url="/prova-vocale")

    @app.get("/tech", response_class=HTMLResponse, include_in_schema=False)
    async def tech_page() -> str:
        """Scheda tecnica stampabile (dossier cliente): http://localhost:8003/tech."""
        from pathlib import Path

        return (Path(__file__).with_name("tech.html")).read_text(encoding="utf-8")

    @app.get("/prova-vocale", response_class=HTMLResponse, include_in_schema=False)
    async def voice_test_page() -> str:
        """Pagina di test microfono (solo localhost/HTTPS per i limiti browser)."""
        from pathlib import Path

        return _voice_page(Path(__file__).with_name("voice_test.html"), test=False,
                           be_url=settings.backend_base_url)

    @app.get("/prova-vocale-test", response_class=HTMLResponse, include_in_schema=False)
    async def voice_test_local_page() -> str:
        """Variante TEST: stessa pagina, titolo VOICE/TESTS + BE dichiarato.

        Usala puntando QUESTA istanza a un BE locale (stub `tests/stub_be.py`
        o BE in locale via BACKEND_BASE_URL): dal banner vedi subito quale BE usa.
        """
        from pathlib import Path

        return _voice_page(Path(__file__).with_name("voice_test.html"), test=True,
                           be_url=settings.backend_base_url)

    @app.get("/tech-codice", response_class=HTMLResponse, include_in_schema=False)
    async def tech_code_page() -> str:
        """Scheda divulgativa: logica del codice con pipeline e file (per tecnici)."""
        from pathlib import Path

        return (Path(__file__).with_name("tech_codice.html")).read_text(encoding="utf-8")

    @app.get("/tech-idea", response_class=HTMLResponse, include_in_schema=False)
    async def tech_idea_page() -> str:
        """Scheda divulgativa: l'idea in parole semplici (per non tecnici)."""
        from pathlib import Path

        return (Path(__file__).with_name("tech_idea.html")).read_text(encoding="utf-8")

    @app.get("/ready")
    async def ready() -> Any:
        backend = BackendClient(
            base_url=settings.backend_base_url,
            timeout_s=5.0,
            api_key=settings.backend_api_key,
        )
        try:
            ok = await backend.health()
        finally:
            await backend.aclose()
        if ok:
            return {"status": "ready", "backend": settings.backend_base_url}
        return JSONResponse({"status": "degraded", "backend": settings.backend_base_url}, status_code=503)

    @app.get("/diag")
    async def diag() -> dict[str, object]:
        """Diagnosi live per il pannello STATO: voice + BE + modello, in un colpo solo."""
        import httpx

        be: dict[str, object] = {"ok": False, "detail": "non raggiunto", "model": ""}
        base = settings.backend_base_url.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                for path in ("/api/health", "/health"):
                    try:
                        resp = await client.get(base + path)
                    except Exception as exc:
                        be["detail"] = f"{type(exc).__name__}: {exc}"
                        continue
                    if resp.status_code != 200:
                        be["detail"] = f"HTTP {resp.status_code} su {path}"
                        continue
                    try:
                        body = resp.json()
                    except ValueError:
                        body = {}
                    be = {"ok": True, "detail": f"200 su {path}",
                          "model": str(body.get("llm_model", body.get("model", "")) or "")}
                    break
        except Exception as exc:
            be["detail"] = f"{type(exc).__name__}: {exc}"
        return {
            "voice": "ok",
            "be_url": base,
            "be": be,
            "stt_backend": settings.stt_backend,
            "tts_backend": settings.tts_backend,
            "sample_rate": settings.sample_rate,
            "tts_sample_rate": settings.tts_sample_rate,
        }

    @app.websocket("/ws/voice")
    async def ws_voice(ws: WebSocket) -> None:
        await ws.accept()
        session = _make_session(settings, ws)
        log.info("ws open session=%s", session.session_id)
        run_task = asyncio.create_task(session.run())
        try:
            await ws.send_text(json.dumps({"event": "ready", "session_id": session.session_id,
                                           "sample_rate": settings.sample_rate,
                                           "tts_sample_rate": settings.tts_sample_rate}))
            await _reader(ws, session, settings)
        except WebSocketDisconnect:
            log.info("ws disconnect session=%s", session.session_id)
        except Exception as exc:
            log.error("ws error session=%s err=%s", session.session_id, exc)
        finally:
            await session.close()
            # Wake writer blocked on next_output with EOS.
            with contextlib.suppress(Exception):
                await session.audio_out_q.put(None)
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await run_task
            with contextlib.suppress(Exception):
                await ws.close()

    async def _writer(ws: WebSocket, session: VoiceSession) -> None:
        """Drain audio_out_q -> websocket (started lazily by reader)."""
        try:
            while True:
                chunk = await session.next_output()
                if chunk is None:
                    return
                await ws.send_bytes(chunk)
        except (WebSocketDisconnect, asyncio.CancelledError):
            raise
        except Exception as exc:
            log.error("writer err session=%s err=%s", session.session_id, exc)

    async def _reader(ws: WebSocket, session: VoiceSession, settings: Settings) -> None:
        writer = asyncio.create_task(_writer(ws, session))
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=60.0)
                except asyncio.TimeoutError:
                    log.info("ws idle timeout session=%s", session.session_id)
                    break
                if msg.get("bytes") is not None:
                    await session.push_audio(bytes(msg["bytes"]))
                elif msg.get("text") is not None:
                    try:
                        cmd = json.loads(str(msg["text"]))
                    except ValueError:
                        continue
                    if cmd.get("cmd") == "eos":
                        await session.push_audio(None)
                        break
                    if cmd.get("cmd") == "reset":
                        session.llm.reset()
                        session.vad.reset()
        finally:
            writer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await writer

    return app


def _make_session(settings: Settings, ws: WebSocket) -> VoiceSession:
    backend = BackendClient(
        base_url=settings.backend_base_url,
        timeout_s=settings.backend_timeout_s,
        api_key=settings.backend_api_key,
        chat_stream_path=settings.backend_chat_stream_path,
    )
    orchestrator = BackendOrchestrator(
        backend=backend,
        system_prompt=settings.llm_system_prompt,
        max_history=settings.llm_max_history,
        token_timeout_s=settings.llm_token_timeout_s,
    )

    async def send_control(payload: dict[str, str]) -> None:
        with contextlib.suppress(Exception):
            await ws.send_text(json.dumps(payload))

    def _cb(payload: dict[str, str]) -> asyncio.Future[object] | object | None:
        return asyncio.ensure_future(send_control(payload))  # type: ignore[return-value]

    return VoiceSession(
        vad=build_vad(  # type: ignore[arg-type]
            settings.vad_mode,
            threshold=settings.vad_energy_threshold,
            silence_ms=settings.vad_silence_ms,
            min_speech_ms=settings.vad_min_speech_ms,
            max_segment_s=settings.vad_max_segment_s,
            sample_rate=settings.sample_rate,
            frame_ms=settings.frame_ms,
        ),
        stt=build_stt(
            settings.stt_backend,
            model=settings.stt_model,
            device=settings.stt_device,
            compute_type=settings.stt_compute_type,
            language=settings.stt_language,
        ),
        llm=orchestrator,
        tts=build_tts(
            settings.tts_backend,
            model_path=settings.piper_model_path,
            config_path=settings.piper_config_path,
            sample_rate=settings.tts_sample_rate,
        ),
        sample_rate=settings.sample_rate,
        audio_in_max=settings.audio_in_queue_max,
        text_max=settings.text_queue_max,
        audio_out_max=settings.audio_out_queue_max,
        barge_in_enabled=settings.barge_in_enabled,
        on_control=_cb,
    )


app = build_app()
