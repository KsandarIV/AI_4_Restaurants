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


def build_app(settings: Settings | None = None) -> FastAPI:
    """Create the FastAPI app with injected settings (test-friendly)."""
    settings = settings or get_settings()
    setup_logging(settings.log_level)
    app = FastAPI(title="Voice-bot Ristorante (Traccia 3)")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/tech", response_class=HTMLResponse, include_in_schema=False)
    async def tech_page() -> str:
        """Scheda tecnica stampabile (dossier cliente): http://localhost:8003/tech."""
        from pathlib import Path

        return (Path(__file__).with_name("tech.html")).read_text(encoding="utf-8")

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

    @app.websocket("/ws/voice")
    async def ws_voice(ws: WebSocket) -> None:
        await ws.accept()
        session = _make_session(settings, ws)
        log.info("ws open session=%s", session.session_id)
        run_task = asyncio.create_task(session.run())
        try:
            await ws.send_text(json.dumps({"event": "ready", "session_id": session.session_id,
                                           "sample_rate": settings.sample_rate}))
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
