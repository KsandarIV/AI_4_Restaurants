"""The BE gateway: one origin, star topology (CHAT and VOICE only ever talk to the BE), HTTPS for the microphone."""

from __future__ import annotations

import asyncio
import json
import socket
import sys
import threading
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
import websockets
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from showcase import gateway, tls  # noqa: E402


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def _run(app: FastAPI, **ssl_kwargs: Any) -> Iterator[int]:
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", **ssl_kwargs))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        thread.join(0.05)
    try:
        yield port
    finally:
        server.should_exit = True
        thread.join(5)


def fake_be() -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "online", "restaurant": "Bella Napoli"}

    @app.get("/api/staff/reservations")
    def staff(request: Request) -> Any:
        if request.headers.get("x-api-key") != "secret":
            return JSONResponse({"detail": "forbidden"}, status_code=401)
        return [{"booking_code": "RES-1", "customer_name": "Mario Rossi"}]

    @app.get("/docs")
    def docs() -> dict[str, str]:
        return {"swagger": "yes"}

    return app


def fake_voice(hits: list[str]) -> FastAPI:
    app = FastAPI()

    @app.get("/site/menu")
    def menu() -> list[dict[str, str]]:
        hits.append("menu")
        return [{"name": "Bruschetta"}]

    @app.get("/diag")
    def diag() -> dict[str, str]:
        return {"voice": "ok"}

    @app.post("/site/chat/session")
    def chat_via_voice() -> dict[str, str]:  # must NEVER be used: that would be VOICE -> CHAT
        hits.append("voice-chat-bridge")
        return {"reply": "wrong path"}

    @app.websocket("/ws/voice")
    async def ws(sock: WebSocket) -> None:
        await sock.accept()
        await sock.send_text(json.dumps({"event": "ready", "tts_sample_rate": 16000}))
        while True:
            msg = await sock.receive()
            if msg["type"] == "websocket.disconnect":
                return
            if msg.get("bytes") is not None:
                await sock.send_bytes(b"echo:" + msg["bytes"])
            elif msg.get("text") == "bye":
                await sock.close()
                return

    return app


def fake_chat(hits: list[str]) -> FastAPI:
    app = FastAPI()

    @app.post("/chat/session")
    def session() -> dict[str, str]:
        hits.append("chat-session")
        return {"session_id": "s1", "phase": "registration", "reply": "Benvenuto!"}

    @app.post("/chat/message")
    async def message(request: Request) -> dict[str, str]:
        body = await request.json()
        hits.append("chat-message")
        return {"reply": f"eco: {body['text']}", "phase": "chat"}

    return app


@asynccontextmanager
async def star(voice_up: bool = True) -> AsyncIterator[tuple[str, dict[str, list[str]]]]:
    """BE gateway + fake BE + fake VOICE + fake CHAT, each on its own port."""
    hits: dict[str, list[str]] = {"voice": [], "chat": []}
    with _run(fake_be()) as be_port, _run(fake_voice(hits["voice"])) as voice_port, _run(fake_chat(hits["chat"])) as chat_port:
        voice = f"http://127.0.0.1:{voice_port}" if voice_up else ""
        app = gateway.create_gateway(f"http://127.0.0.1:{be_port}", lambda: voice, lambda: f"http://127.0.0.1:{chat_port}")
        with _run(app) as gw_port:
            yield f"http://127.0.0.1:{gw_port}", hits


async def test_the_gateway_serves_the_complete_site_with_its_own_origin() -> None:
    async with star() as (gw, _), httpx.AsyncClient() as client:
        html = (await client.get(gw + "/")).text
        assert f'window.VOICE_BASE = "{gw}/voice"' in html  # one absolute origin: voice, chat and staff all behind it
        for link in ('href="/staff.html"', 'href="' + gw + '/docs"', 'href="' + gw + '/voice/diag"'):
            assert link in html, link
        assert (await client.get(gw + "/site-assets/app.js")).status_code == 200
        health = (await client.get(gw + "/health")).json()
        assert health["gateway"] is True and health["version"] == gateway.VERSION and health["voice"] and health["chat"]


async def test_database_and_staff_area_go_through_the_gateway_to_the_be() -> None:
    async with star() as (gw, _), httpx.AsyncClient() as client:
        assert (await client.get(gw + "/api/health")).json()["restaurant"] == "Bella Napoli"
        assert (await client.get(gw + "/api/staff/reservations")).status_code == 401  # upstream status passes through
        ok = await client.get(gw + "/api/staff/reservations", headers={"X-API-Key": "secret"})
        assert ok.json()[0]["customer_name"] == "Mario Rossi"  # the key reaches the BE: the gateway adds no auth bypass
        assert (await client.get(gw + "/docs")).json() == {"swagger": "yes"}
        staff_page = await client.get(gw + "/staff.html")
        assert staff_page.status_code == 200 and "Area ristoratore" in staff_page.text
        assert f'baseUrl: "{gw}"' in (await client.get(gw + "/js/config.js")).text  # the staff page talks to this origin


async def test_voice_http_is_proxied_under_voice() -> None:
    async with star() as (gw, hits), httpx.AsyncClient() as client:
        assert (await client.get(gw + "/voice/site/menu")).json() == [{"name": "Bruschetta"}]
        assert (await client.get(gw + "/voice/diag")).json() == {"voice": "ok"}
        assert hits["voice"] == ["menu"]


async def test_the_chat_window_goes_be_to_chat_never_voice_to_chat() -> None:
    async with star() as (gw, hits), httpx.AsyncClient() as client:
        session = (await client.post(gw + "/voice/site/chat/session")).json()
        assert session["session_id"] == "s1"
        said = (await client.post(gw + "/voice/site/chat/message", json={"session_id": "s1", "text": "ciao"})).json()
        assert said["reply"] == "eco: ciao"
        assert hits["chat"] == ["chat-session", "chat-message"]
        assert "voice-chat-bridge" not in hits["voice"]  # the topology rule: CHAT and VOICE never talk directly
        assert (await client.post(gw + "/voice/site/chat/other")).status_code == 404


async def test_websocket_is_proxied_in_both_directions() -> None:
    async with star() as (gw, _):
        async with websockets.connect(gw.replace("http", "ws") + "/voice/ws/voice") as ws:
            assert json.loads(await asyncio.wait_for(ws.recv(), 5))["event"] == "ready"
            await ws.send(b"\x01\x02\x03")
            assert await asyncio.wait_for(ws.recv(), 5) == b"echo:\x01\x02\x03"
            await ws.send("bye")  # the upstream hangs up: the client sees the call end
            with pytest.raises(websockets.ConnectionClosed):
                await asyncio.wait_for(ws.recv(), 5)


async def test_a_missing_voice_pc_is_a_clean_502_and_a_closed_socket() -> None:
    async with star(voice_up=False) as (gw, _), httpx.AsyncClient() as client:
        down = await client.get(gw + "/voice/site/menu")
        assert down.status_code == 502 and "non raggiungibile" in down.json()["detail"]
        async with websockets.connect(gw.replace("http", "ws") + "/voice/ws/voice") as ws:
            with pytest.raises(websockets.ConnectionClosed):
                await asyncio.wait_for(ws.recv(), 5)
        assert (await client.get(gw + "/health")).json()["voice"] is None


async def test_static_serving_is_confined_to_css_and_js() -> None:
    async with star() as (gw, _), httpx.AsyncClient() as client:
        assert (await client.get(gw + "/css/style.css")).status_code == 200
        for bad in ("/css/..%2fREADME.md", "/js/..%2f..%2f.env", "/site-assets/..%2f..%2f..%2fserver.py"):
            assert (await client.get(gw + bad)).status_code in (404, 400), bad


def test_peer_cache_resolves_lazily_and_misses_are_retried_soon(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter(["", "10.10.95.60"])
    monkeypatch.setattr(gateway.peers, "resolve", lambda *a, **k: next(answers))
    cache = gateway.PeerCache("voice", "10.10.95.34", "10.10.95.34")
    assert cache() == ""  # the voice PC is not up yet
    cache._until = 0.0  # the short miss TTL elapsed
    assert cache() == "http://10.10.95.60:8003"  # picked up without restarting the gateway
    assert gateway.PeerCache("chat", "", "", fixed="http://x:8002/")() == "http://x:8002"


# ---------------- TLS ----------------


@pytest.fixture()
def tls_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(tls, "TLS_DIR", tmp_path)
    monkeypatch.setattr(tls, "CERT", tmp_path / "gateway.pem")
    monkeypatch.setattr(tls, "KEY", tmp_path / "gateway.key")
    monkeypatch.setattr(tls, "SAN_FILE", tmp_path / "gateway.san.json")
    return tmp_path


def test_certificate_covers_every_name_the_gateway_is_reached_by(tls_dir: Path) -> None:
    material = tls.ensure_certificate(["10.10.95.34"])
    if material is None:
        pytest.skip("no tool to create a certificate on this machine")
    san = json.loads((tls_dir / "gateway.san.json").read_text())
    assert {"localhost", "completo.localhost", "127.0.0.1", "10.10.95.34"} <= set(san)
    first = material[0].read_bytes()
    assert tls.ensure_certificate(["10.10.95.34"]) == material and material[0].read_bytes() == first  # idempotent
    tls.ensure_certificate(["10.10.95.99"])  # the BE got a new address: certificate re-issued with it
    assert "10.10.95.99" in json.loads((tls_dir / "gateway.san.json").read_text())


def test_an_operator_supplied_certificate_is_never_overwritten(tls_dir: Path) -> None:
    (tls_dir / "gateway.pem").write_text("CA-ISSUED")
    (tls_dir / "gateway.key").write_text("KEY")
    assert tls.ensure_certificate(["10.10.95.34"]) is not None
    assert (tls_dir / "gateway.pem").read_text() == "CA-ISSUED"


async def test_the_gateway_really_speaks_https(tls_dir: Path) -> None:
    material = tls.ensure_certificate([])
    if material is None:
        pytest.skip("no tool to create a certificate on this machine")
    app = gateway.create_gateway("http://127.0.0.1:9", lambda: "", lambda: "")
    with _run(app, ssl_certfile=str(material[0]), ssl_keyfile=str(material[1])) as port:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(f"https://127.0.0.1:{port}/health")
        assert response.status_code == 200 and response.json()["gateway"] is True
        with pytest.raises(httpx.HTTPError):  # a client that checks the chain refuses the self-signed certificate
            async with httpx.AsyncClient(verify=True) as strict:
                await strict.get(f"https://127.0.0.1:{port}/health")
