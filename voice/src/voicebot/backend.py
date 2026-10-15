"""Async HTTP client toward the BE (a separate LAN machine, ``backend/api/routes.py``).

Contract actually used by the voice bot (same endpoints as the chat bot):

  GET  /api/health                  readiness + model info
  POST /api/customers               {name, phone, consent} -> {customer_id}
  POST /api/chat                    {message, session_id, customer_id, client_type} -> {reply}
  POST /api/chat/stream             same body; SSE ``data: {"token": ".."}`` ... ``data: [DONE]``
                                    (the BE runs the whole LLM turn first, then streams the
                                    words, so the first token costs one full inference)

Resilience: every call has timeouts; idempotent calls retry with exponential backoff; the
non-idempotent ``POST /api/chat`` is retried only when the connection could not even be
established (a retry after a read timeout could book a table twice).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .logging_json import get_logger
from .pii import scrub_pii

log = get_logger("backend")


class BackendError(RuntimeError):
    """The BE failed in a way the caller should turn into an apology."""

    def __init__(self, message: str, status: int | None = None, kind: str = "http") -> None:
        super().__init__(message)
        self.status = status  # HTTP status when there was a response
        self.kind = kind  # "unreachable" | "timeout" | "http" | "format"


def _backoff(attempt: int) -> float:
    return float(min(0.5 * 2.0**attempt, 4.0))


class BackendClient:
    """Resilient async client for the BE."""

    def __init__(
        self,
        base_url: str,
        timeout_s: float = 15.0,
        api_key: str = "",
        chat_stream_path: str = "/api/chat/stream",
        max_retries: int = 3,
        chat_timeout_s: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout_s, connect=min(5.0, timeout_s))
        self._chat_timeout = httpx.Timeout(chat_timeout_s, connect=min(5.0, timeout_s))
        self._api_key = api_key
        self._chat_stream_path = chat_stream_path
        self._max_retries = max(1, max_retries)
        self._client = httpx.AsyncClient(base_url=self._base, timeout=self._timeout, transport=transport)

    @property
    def base_url(self) -> str:
        """The BE address this client talks to."""
        return self._base

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: httpx.Timeout | None = None,
    ) -> Any:
        """One HTTP call with retry/backoff. Returns the parsed JSON body."""
        idempotent = method.upper() in ("GET", "HEAD", "DELETE", "PUT")
        last: Exception | None = None
        kind = "unreachable"
        for attempt in range(1, self._max_retries + 1):
            try:
                resp = await self._client.request(
                    method, path, headers=self._headers(), json=json_body, params=params,
                    timeout=timeout or self._timeout,
                )
                if resp.status_code >= 500 and idempotent and attempt < self._max_retries:
                    log.warning("backend %s %s -> %d, retry %d", method, path, resp.status_code, attempt)
                    await asyncio.sleep(_backoff(attempt))
                    continue
                if resp.status_code >= 400:
                    raise BackendError(
                        f"BE {resp.status_code} on {method} {path}: {resp.text[:200]}",
                        status=resp.status_code,
                    )
                if not resp.content:
                    return {}
                try:
                    return resp.json()
                except ValueError as exc:
                    raise BackendError(f"BE returned invalid JSON on {path}", kind="format") from exc
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last = exc  # never reached the BE: always safe to retry
                kind = "unreachable"
            except httpx.TimeoutException as exc:
                last = exc
                kind = "timeout"
                if not idempotent:
                    raise BackendError(f"BE timeout on {method} {path}", kind=kind) from exc
            except httpx.TransportError as exc:
                last = exc
                kind = "unreachable"
                if not idempotent:
                    raise BackendError(f"BE connection lost on {method} {path}: {exc}", kind=kind) from exc
            if attempt < self._max_retries:
                log.warning("backend retry %d/%d %s %s: %s", attempt, self._max_retries, method, path, last)
                await asyncio.sleep(_backoff(attempt))
        raise BackendError(
            f"BE unreachable after {self._max_retries} attempts: {last}", kind=kind
        )

    # ---------------- public API ----------------

    async def health_info(self) -> dict[str, Any]:
        """``GET /api/health`` (falls back to ``/health``). Raises BackendError."""
        try:
            data = await self._request("GET", "/api/health")
        except BackendError as exc:
            if exc.status != 404:
                raise
            data = await self._request("GET", "/health")
        return data if isinstance(data, dict) else {}

    async def health(self) -> bool:
        """True when the BE answers its health check."""
        try:
            await self.health_info()
            return True
        except BackendError:
            return False

    async def get_info(self) -> Any:
        """``GET /api/info`` (restaurant address, phone, hours)."""
        return await self._request("GET", "/api/info")

    async def register_customer(self, name: str, phone: str) -> str:
        """Register name + phone (E.164) and return the anonymous ``customer_id``.

        This is the ONLY call that carries personal data, exactly as in the chat bot.
        """
        log.info("register_customer phone=%s", phone[:4] + "***")  # never log personal data
        data = await self._request(
            "POST", "/api/customers", json_body={"name": name, "phone": phone, "consent": True}
        )
        customer_id = data.get("customer_id") if isinstance(data, dict) else None
        if not customer_id:
            raise BackendError("BE /api/customers: unexpected response", kind="format")
        return str(customer_id)

    async def chat(
        self,
        message: str,
        session_id: str,
        customer_id: str,
        client_type: str = "voice",
    ) -> dict[str, Any]:
        """Non-streaming turn (``POST /api/chat``): one complete reply for one question."""
        payload = {
            "message": scrub_pii(message),
            "session_id": session_id,
            "customer_id": customer_id,
            "client_type": client_type,
        }
        result = await self._request(
            "POST", "/api/chat", json_body=payload, timeout=self._chat_timeout
        )
        if not isinstance(result, dict) or "reply" not in result:
            raise BackendError(f"BE /api/chat: unexpected response: {result!r:.200}", kind="format")
        return result

    async def stream_chat(
        self,
        message: str,
        session_id: str,
        customer_id: str,
        client_type: str = "voice",
        system_prompt: str = "",
    ) -> AsyncIterator[str]:
        """Yield the reply token by token from the SSE endpoint.

        If the connection fails *before the first token* it reconnects once; after the
        first token a failure ends the stream (replaying would repeat words aloud).
        """
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": scrub_pii(message)})
        payload = {
            "messages": messages,
            "stream": True,
            "session_id": session_id,
            "customer_id": customer_id,
            "client_type": client_type,
        }
        started = False
        for attempt in (1, 2):
            try:
                async with self._client.stream(
                    "POST", self._chat_stream_path, headers=self._headers(),
                    json=payload, timeout=self._chat_timeout,
                ) as resp:
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode("utf-8", "replace")[:200]
                        raise BackendError(
                            f"BE {resp.status_code} on stream: {body}", status=resp.status_code
                        )
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            return
                        try:
                            obj = json.loads(data)
                        except ValueError:
                            continue
                        token = obj.get("token") or obj.get("content") or obj.get("delta") or ""
                        if token:
                            started = True
                            yield str(token)
                    return
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                if attempt == 2:
                    raise BackendError(f"BE unreachable: {exc}", kind="unreachable") from exc
                log.warning("chat stream reconnect: %s", exc)
                await asyncio.sleep(_backoff(attempt))
            except httpx.TimeoutException as exc:
                raise BackendError("BE timeout while streaming", kind="timeout") from exc
            except httpx.TransportError as exc:
                if started or attempt == 2:
                    raise BackendError(f"BE stream lost: {exc}", kind="unreachable") from exc
                log.warning("chat stream reconnect: %s", exc)
                await asyncio.sleep(_backoff(attempt))

    async def aclose(self) -> None:
        """Close the underlying HTTP connections."""
        await self._client.aclose()
