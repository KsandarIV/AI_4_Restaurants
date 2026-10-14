"""Async HTTP client toward the BE (separate LAN machine).

Contract (configurable, documented here and in README):
  GET  {base}/health
  GET  {base}/api/menu
  GET  {base}/api/info
  GET  {base}/api/availability?date=YYYY-MM-DD&time=HH:MM&party_size=N
  POST {base}/api/reservations            {date,time,party_size,name}
  PUT  {base}/api/reservations/{id}       {date?,time?,party_size?}
  DELETE {base}/api/reservations/{id}
  POST {base}/chat/stream  (SSE: lines `data: {"token": "..."}` + `data: [DONE]`)

All requests have timeouts + exponential-backoff retries (re-connection logic).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import httpx

from .logging_json import get_logger
from .pii import scrub_pii

log = get_logger("backend")


class BackendError(RuntimeError):
    """Non-retryable or exhausted BE failure."""


class BackendClient:
    """Resilient async client for the BE with retry/backoff on every call."""

    def __init__(
        self,
        base_url: str,
        timeout_s: float = 15.0,
        api_key: str = "",
        chat_stream_path: str = "/api/chat/stream",
        max_retries: int = 3,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout_s)
        self._api_key = api_key
        self._chat_path = chat_stream_path
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(base_url=self._base, timeout=self._timeout)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """HTTP request with scrub + exponential backoff. Returns parsed JSON."""
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                resp = await self._client.request(method, path, headers=self._headers(), **kwargs)
                resp.raise_for_status()
                if not resp.content:
                    return {}
                try:
                    return resp.json()
                except ValueError:
                    return {"raw": resp.text}
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                log.warning("backend retry %d/%d %s %s: %s", attempt, self._max_retries, method, path, exc)
                await asyncio.sleep(min(2.0**attempt, 8.0))
            except httpx.HTTPStatusError as exc:
                if exc.response is not None and 500 <= exc.response.status_code < 600 and attempt < self._max_retries:
                    last_exc = exc
                    await asyncio.sleep(min(2.0**attempt, 8.0))
                    continue
                raise BackendError(f"BE {exc.response.status_code if exc.response else '?'}: {exc}") from exc
        raise BackendError(f"BE unreachable after {self._max_retries} attempts: {last_exc}")

    async def health(self) -> bool:
        """Return True when the BE answers."""
        try:
            await self._request("GET", "/health")
            return True
        except BackendError:
            return False

    async def get_menu(self) -> Any:
        """Fetch restaurant menu."""
        return await self._request("GET", "/api/menu")

    async def get_info(self) -> Any:
        """Fetch position/contacts/hours."""
        return await self._request("GET", "/api/info")

    async def check_availability(self, date: str, time: str, party_size: int) -> Any:
        """Check table availability."""
        return await self._request(
            "GET", "/api/availability", params={"date": date, "time": time, "party_size": party_size}
        )

    async def create_reservation(self, date: str, time: str, party_size: int, name: str) -> Any:
        """Create a reservation (name is PII-scrubbed in logs, sent as given per BE contract)."""
        log.info("create_reservation date=%s time=%s party=%d name=%s", date, time, party_size, scrub_pii(name))
        return await self._request(
            "POST", "/api/reservations",
            content=json.dumps({"date": date, "time": time, "party_size": party_size, "name": name}),
        )

    async def stream_chat(
        self, messages: list[dict[str, str]], timeout_s: float = 30.0
    ) -> AsyncIterator[str]:
        """Yield LLM tokens from the BE SSE stream with auto-reconnect (1 retry).

        BE streams ``data: {"token": "..."}`` lines terminated by ``data: [DONE]``.
        """
        payload = {"messages": [{"role": m["role"], "content": scrub_pii(m["content"])} for m in messages],
                   "stream": True}
        for attempt in (1, 2):
            try:
                async with self._client.stream(
                    "POST", self._chat_path, headers=self._headers(),
                    content=json.dumps(payload), timeout=httpx.Timeout(timeout_s),
                ) as resp:
                    resp.raise_for_status()
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
                            yield str(token)
                    return
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                log.warning("chat stream reconnect attempt=%d err=%s", attempt, exc)
                if attempt == 2:
                    raise BackendError(f"chat stream failed: {exc}") from exc
                await asyncio.sleep(1.0 * attempt)

    async def aclose(self) -> None:
        """Close underlying HTTP connections."""
        await self._client.aclose()
