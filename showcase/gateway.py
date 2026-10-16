"""BE gateway: ONE entry point (https://<BE>:8090) that serves the complete site and reverse-proxies the other services.

Topology (star, as the brief wants: CHAT and VOICE never talk to each other, only through the BE):

    browser (any PC) --HTTPS--> BE gateway :8090 --+--> BE API      127.0.0.1:8000   /api/*, /docs   (DB, staff area, Swagger)
                                                    +--> VOICE PC   :8003            /voice/*  incl. WebSocket /voice/ws/voice
                                                    +--> CHAT PC    :8002            /voice/site/chat/*  (the chat window)

Why a reverse proxy and not "every PC serves its own copy":
  * one origin  -> no CORS, one certificate, one place to add authentication / rate limiting / logging later;
  * the browser never needs to know where VOICE and CHAT live, they can move (DHCP) without touching any client;
  * HTTPS terminates here, which is what gives the CHAT and VOICE PCs a secure context (microphone) over the LAN.

Upstream addresses are resolved lazily and verified (``showcase.peers``): the gateway can start before the other PCs.

    python showcase/gateway.py [--port 8090] [--be http://127.0.0.1:8000] [--no-tls]
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx
import websockets
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, Response

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from showcase import peers, serve  # noqa: E402

VERSION = 3
_HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
               "transfer-encoding", "upgrade", "host", "content-length", "content-encoding"}
_TTL_OK_S, _TTL_MISS_S = 15.0, 3.0

Resolver = Callable[[], str]  # returns "http://host:port" or ""


class PeerCache:
    """Lazily resolved, verified upstream; positive answers live longer than misses so a late PC is picked up quickly."""

    def __init__(self, role: str, own_ip: str, be_host: str, fixed: str = "") -> None:
        self.role, self._own_ip, self._be_host, self._fixed = role, own_ip, be_host, fixed.rstrip("/")
        self._value, self._until = "", 0.0

    def peek(self) -> str:
        """The last resolved address, without probing or scanning (for /health, which must always answer fast)."""
        return self._fixed or self._value

    def __call__(self) -> str:
        if self._fixed:
            return self._fixed
        now = time.monotonic()
        if now >= self._until:
            host = peers.resolve(self.role, own_role="be", own_ip=self._own_ip, be_host=self._be_host, allow_scan=True)
            port = peers.SIGNATURE[self.role][0]
            self._value = f"http://{host}:{port}" if host else ""
            self._until = now + (_TTL_OK_S if host else _TTL_MISS_S)
        return self._value


def static_response(base: Path, rel: str) -> Response:
    """A file of ``base`` (read-only, confined: ``..`` cannot leave the folder)."""
    target = (base / rel).resolve()
    if base.resolve() in target.parents and target.is_file():
        return Response(target.read_bytes(), headers={"Content-Type": serve._mime(target.name), "Cache-Control": "no-store"})
    return Response("not found", status_code=404, media_type="text/plain")


def _clean(headers: Any) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in _HOP_BY_HOP}


def create_gateway(be_url: str, voice: Resolver, chat: Resolver) -> FastAPI:
    """Build the gateway app (resolvers injected: tests use fixed upstreams)."""
    client = httpx.AsyncClient(timeout=httpx.Timeout(130.0, connect=4.0))

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await client.aclose()

    app = FastAPI(title="AI4Restaurants BE gateway", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    be_url = be_url.rstrip("/")

    async def forward(base: str, path: str, request: Request, body: bytes | None = None) -> Response:
        if not base:
            return JSONResponse({"detail": "Servizio non raggiungibile: il PC non risponde."}, status_code=502)
        try:
            upstream = await client.request(
                request.method, f"{base}/{path}", params=request.query_params,
                content=await request.body() if body is None else body, headers=_clean(request.headers),
            )
        except httpx.HTTPError:
            return JSONResponse({"detail": "Servizio non raggiungibile."}, status_code=502)
        return Response(upstream.content, status_code=upstream.status_code, headers=_clean(upstream.headers),
                        media_type=upstream.headers.get("content-type"))

    def origin(request: Request) -> str:
        return f"{request.url.scheme}://{request.headers.get('host', request.url.netloc)}"

    @app.get("/health")
    async def health() -> dict[str, Any]:
        peek = getattr(voice, "peek", voice), getattr(chat, "peek", chat)  # never block a health check on a LAN scan
        v, c = peek[0](), peek[1]()
        return {"status": "ok", "version": VERSION, "gateway": True, "be": be_url, "voice": v or None, "chat": c or None}

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> Response:
        o = origin(request)
        return HTMLResponse(serve.render_index(f"{o}/voice", o, gateway=True).decode("utf-8"))

    @app.get("/site-assets/{rel:path}")
    async def assets(rel: str) -> Response:
        return static_response(serve.SITE_DIR, rel)

    @app.get("/staff.html")
    async def staff() -> Response:
        return static_response(serve.FRONTEND_DIR, "staff.html")

    @app.get("/js/config.js")
    async def config_js(request: Request) -> Response:  # the staff page talks to THIS origin: /api/* is proxied to the BE
        return Response(serve.render_config_js(origin(request)), media_type="application/javascript; charset=utf-8")

    @app.get("/js/{rel:path}")
    async def js(rel: str) -> Response:
        return static_response(serve.FRONTEND_DIR / "js", rel)

    @app.get("/css/{rel:path}")
    async def css(rel: str) -> Response:
        return static_response(serve.FRONTEND_DIR / "css", rel)

    # ---- BE: database, staff area, Swagger ----
    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"])
    async def be_api(path: str, request: Request) -> Response:
        return await forward(be_url, f"api/{path}", request)

    @app.get("/docs")
    @app.get("/openapi.json")
    async def be_docs(request: Request) -> Response:
        return await forward(be_url, request.url.path.lstrip("/"), request)

    # ---- CHAT: the chat window goes BE -> CHAT, never VOICE -> CHAT ----
    @app.post("/voice/site/chat/{action}")
    async def chat_window(action: str, request: Request) -> Response:
        if action not in ("session", "message"):
            return JSONResponse({"detail": "not found"}, status_code=404)
        base = await asyncio.to_thread(chat)
        return await forward(base, f"chat/{action}", request)

    # ---- VOICE: HTTP + WebSocket ----
    @app.api_route("/voice/{path:path}", methods=["GET", "POST", "OPTIONS"])
    async def voice_http(path: str, request: Request) -> Response:
        return await forward(await asyncio.to_thread(voice), path, request)

    @app.websocket("/voice/ws/voice")
    async def voice_ws(ws: WebSocket) -> None:
        base = await asyncio.to_thread(voice)
        await ws.accept()
        if not base:
            await ws.close(code=1013)  # try again later
            return
        try:
            async with websockets.connect(base.replace("http", "ws", 1) + "/ws/voice", max_size=None,
                                          open_timeout=8) as upstream:
                async def down_to_up() -> None:
                    while True:
                        msg = await ws.receive()
                        if msg["type"] == "websocket.disconnect":
                            return
                        if msg.get("bytes") is not None:
                            await upstream.send(msg["bytes"])
                        elif msg.get("text") is not None:
                            await upstream.send(msg["text"])

                async def up_to_down() -> None:
                    async for msg in upstream:
                        if isinstance(msg, bytes):
                            await ws.send_bytes(msg)
                        else:
                            await ws.send_text(msg)

                tasks = [asyncio.create_task(down_to_up()), asyncio.create_task(up_to_down())]
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                for task in done:
                    task.exception()  # retrieve: a closed socket is the normal way a call ends
        except (OSError, websockets.WebSocketException, asyncio.TimeoutError):
            pass
        finally:
            with contextlib.suppress(Exception):
                await ws.close()

    return app


def main(argv: list[str] | None = None) -> int:
    """Run the gateway (HTTPS when a certificate can be made)."""
    import uvicorn

    from showcase import tls

    parser = argparse.ArgumentParser(description="BE gateway: complete site + reverse proxy to BE, VOICE and CHAT.")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--be", default="http://127.0.0.1:8000")
    parser.add_argument("--no-tls", action="store_true", help="plain HTTP (the microphone then works only on localhost)")
    args = parser.parse_args(argv)
    own_ip, be_host = peers._own_ip(), peers._be_host_from_env()
    app = create_gateway(args.be, PeerCache("voice", own_ip, be_host), PeerCache("chat", own_ip, be_host))
    material = None if args.no_tls else tls.ensure_certificate([own_ip, be_host])
    scheme = "https" if material else "http"
    if not args.no_tls and not material:
        print("[gateway] ATTENZIONE: nessuno strumento per creare il certificato (pip install cryptography): "
              "parto in HTTP, il microfono funzionera' solo da localhost.", flush=True)
    print(f"[gateway] {scheme}://completo.localhost:{args.port}/  e  {scheme}://{own_ip or '<IP-BE>'}:{args.port}/  "
          f"(BE {args.be})", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning",
                ssl_certfile=str(material[0]) if material else None, ssl_keyfile=str(material[1]) if material else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
