"""The whole local flow over real sockets: stub BE <- voice server <- live client."""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
import uvicorn
import websockets

from tests.helpers import loud, silence, stub_be, wait_until
from voicebot.config import Settings
from voicebot.live_client import LiveClient
from voicebot.pipeline.server import create_app
from voicebot.stt import FakeSTT


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@asynccontextmanager
async def voice_server(
    be_url: str, script: list[str] | None = None, port: int | None = None, **overrides: Any
) -> AsyncIterator[tuple[str, Any]]:
    """Run the real voice app under uvicorn; yields (base_http_url, app)."""
    options: dict[str, Any] = {
        "backend_base_url": be_url, "stt_backend": "fake", "tts_backend": "fake",
        "vad_silence_ms": 60, "vad_min_speech_ms": 40, "barge_in_min_ms": 60,
    }
    settings = Settings(**{**options, **overrides})
    app = create_app(settings)
    if script is not None:
        app.state.models.stt = FakeSTT(script=script)
    port = port or _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None, ws="auto"))
    task = asyncio.create_task(server.serve())
    await wait_until(lambda: server.started, timeout=15)
    try:
        yield f"127.0.0.1:{port}", app
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, timeout=15)


class RecordingSpeaker:
    """A speaker that records what it was asked to play."""

    def __init__(self) -> None:
        self.chunks: list[tuple[int, int]] = []
        self.cleared = 0

    def play(self, pcm: bytes, sample_rate: int) -> None:
        self.chunks.append((len(pcm), sample_rate))

    def clear(self) -> None:
        self.cleared += 1

    @property
    def busy(self) -> bool:
        return False

    def close(self) -> None:
        pass


async def test_health_ready_and_diag_endpoints() -> None:
    async with stub_be() as (be_url, _), voice_server(be_url) as (host, _):
        async with httpx.AsyncClient(base_url=f"http://{host}") as client:
            assert (await client.get("/health")).json() == {"status": "ok"}
            await wait_until(lambda: True)
            ready = await client.get("/ready")
            assert ready.status_code == 200 and ready.json()["status"] == "ready"
            diag = (await client.get("/diag")).json()
            assert diag["be"]["ok"] is True and diag["be"]["model"] == "stub-model"
            assert {"name", "status", "detail", "hint"} <= set(diag["checks"][0])
            names = {c["name"] for c in diag["checks"]}
            assert {"python", "backend", "registration", "tts", "stt", "models"} <= names
            assert (await client.get("/prova-vocale")).status_code == 200


async def test_ready_reports_unreachable_backend() -> None:
    async with voice_server("http://127.0.0.1:9") as (host, _):
        async with httpx.AsyncClient(base_url=f"http://{host}") as client:
            ready = await client.get("/ready")
            assert ready.status_code == 503 and ready.json()["status"] == "degraded"
            backend = next(c for c in (await client.get("/diag")).json()["checks"] if c["name"] == "backend")
            assert backend["status"] == "fail" and "BACKEND_BASE_URL" in backend["hint"]


async def test_phone_call_end_to_end_registration_then_booking() -> None:
    """Greeting -> register by voice -> book with confirmation, through real sockets."""
    script = ["Mario Rossi, 333 1234567", "sì", "Vorrei prenotare un tavolo per due", "sì"]
    async with stub_be() as (be_url, state), voice_server(be_url, script) as (host, _):
        frames: asyncio.Queue[bytes | None] = asyncio.Queue()
        speaker = RecordingSpeaker()
        events: list[dict[str, Any]] = []
        client = LiveClient(f"ws://{host}/ws/voice", frames, speaker, events.append, base_delay_s=0.05)
        call = asyncio.create_task(client.run())

        def replies() -> list[str]:
            return [str(e["text"]) for e in events if e.get("event") == "reply"]

        await wait_until(lambda: len(replies()) >= 1)
        assert "nome e cognome" in replies()[0]
        ready = next(e for e in events if e.get("event") == "ready")
        assert ready["tts_sample_rate"] == 22050 and ready["sample_rate"] == 16000
        for k in range(len(script)):
            for _ in range(15):
                frames.put_nowait(loud())
            for _ in range(6):
                frames.put_nowait(silence())
            await wait_until(lambda k=k: len(replies()) >= k + 2)

        assert "Registrazione completata" in replies()[2]
        assert "RES-STUB01" in replies()[4] and "RES-STUB01" in state.reservations
        assert [e["text"] for e in events if e.get("event") == "transcript"] == script
        assert speaker.chunks and all(rate == 22050 for _, rate in speaker.chunks)
        assert list(state.customers.values())[0]["phone"] == "+393331234567"
        frames.put_nowait(None)  # hang up
        await asyncio.wait_for(call, timeout=10)


async def test_client_reconnects_when_the_server_comes_up_later() -> None:
    port = _free_port()
    frames: asyncio.Queue[bytes | None] = asyncio.Queue()
    client = LiveClient(f"ws://127.0.0.1:{port}/ws/voice", frames, RecordingSpeaker(),
                        base_delay_s=0.05, max_retries=50)
    call = asyncio.create_task(client.run())
    await asyncio.sleep(0.3)  # the server is not there yet: the client must keep trying
    assert client.connections == 0 and not call.done()
    async with stub_be() as (be_url, _), voice_server(be_url, port=port):
        await wait_until(lambda: client.connections == 1, timeout=15)
        frames.put_nowait(None)
        await asyncio.wait_for(call, timeout=10)


async def test_client_gives_up_after_max_retries() -> None:
    client = LiveClient(f"ws://127.0.0.1:{_free_port()}/ws/voice", asyncio.Queue(), RecordingSpeaker(),
                        base_delay_s=0.01, max_retries=1)
    with pytest.raises(ConnectionError):
        await asyncio.wait_for(client.run(), timeout=10)


async def test_client_reconnects_after_the_server_restarts() -> None:
    port = _free_port()
    async with stub_be() as (be_url, _):
        frames: asyncio.Queue[bytes | None] = asyncio.Queue()
        client = LiveClient(f"ws://127.0.0.1:{port}/ws/voice", frames, RecordingSpeaker(),
                            base_delay_s=0.05, max_retries=100)
        call = asyncio.create_task(client.run())
        async with voice_server(be_url, port=port):
            await wait_until(lambda: client.connections == 1, timeout=15)
        await asyncio.sleep(0.2)  # server gone: connection dropped, client is retrying
        async with voice_server(be_url, port=port):
            await wait_until(lambda: client.connections == 2, timeout=15)
            frames.put_nowait(None)  # hang up from inside the second call
            await asyncio.wait_for(call, timeout=10)


async def test_stop_hangs_up_while_waiting_to_reconnect() -> None:
    client = LiveClient(f"ws://127.0.0.1:{_free_port()}/ws/voice", asyncio.Queue(), RecordingSpeaker(),
                        base_delay_s=5.0)
    call = asyncio.create_task(client.run())
    await asyncio.sleep(0.3)
    client.stop()
    await asyncio.wait_for(call, timeout=2)


async def test_barge_in_reaches_the_client_and_clears_its_speaker() -> None:
    from tests.test_pipeline import ScriptedLLM

    async with stub_be() as (be_url, _), voice_server(be_url, ["ciao"]) as (host, app):
        llm = ScriptedLLM(delay_s=5.0)
        import voicebot.pipeline.server as server_module

        original = server_module.make_orchestrator
        server_module.make_orchestrator = lambda settings: llm  # type: ignore[assignment]
        try:
            frames: asyncio.Queue[bytes | None] = asyncio.Queue()
            speaker = RecordingSpeaker()
            events: list[dict[str, Any]] = []
            client = LiveClient(f"ws://{host}/ws/voice", frames, speaker, events.append)
            call = asyncio.create_task(client.run())
            await wait_until(lambda: any(e.get("event") == "reply" for e in events))  # greeting
            await asyncio.sleep(0.5)  # let the greeting finish playing on the client
            for _ in range(15):
                frames.put_nowait(loud())
            for _ in range(6):
                frames.put_nowait(silence())
            await wait_until(lambda: llm.asked == ["ciao"])
            for _ in range(10):  # the caller interrupts the "thinking" bot
                frames.put_nowait(loud())
            await wait_until(lambda: any(e.get("event") == "barge_in" for e in events))
            await wait_until(lambda: llm.cancelled == 1)
            assert speaker.cleared >= 1
            frames.put_nowait(None)
            await asyncio.wait_for(call, timeout=10)
        finally:
            server_module.make_orchestrator = original  # type: ignore[assignment]


async def test_raw_websocket_protocol_and_eos() -> None:
    async with stub_be() as (be_url, _), voice_server(be_url, ["ciao"]) as (host, _):
        async with websockets.connect(f"ws://{host}/ws/voice") as ws:
            first = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            assert first["event"] == "ready" and first["session_id"]
            await ws.send(json.dumps({"cmd": "eos"}))
            with pytest.raises(websockets.ConnectionClosed):
                while True:
                    await asyncio.wait_for(ws.recv(), timeout=10)


async def test_missing_tts_model_is_reported_not_swallowed(tmp_path: Any) -> None:
    async with stub_be() as (be_url, _), voice_server(
        be_url, tts_backend="piper", piper_model_path=str(tmp_path / "nope.onnx")
    ) as (host, _):
        async with httpx.AsyncClient(base_url=f"http://{host}") as client:
            await wait_until(lambda: True)
            await asyncio.sleep(0.3)
            ready = (await client.get("/ready")).json()
            assert ready["status"] == "degraded" and "nope.onnx" in ready["models_error"]
            diag = (await client.get("/diag")).json()
            tts = next(c for c in diag["checks"] if c["name"] == "tts")
            assert tts["status"] == "fail" and "setup_env" in tts["hint"]
        async with websockets.connect(f"ws://{host}/ws/voice") as ws:
            events = []
            with pytest.raises(websockets.ConnectionClosed):
                while True:
                    events.append(json.loads(await asyncio.wait_for(ws.recv(), timeout=10)))
            assert events[-1]["event"] == "error" and events[-1]["detail"] == "models_failed"
