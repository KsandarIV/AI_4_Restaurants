"""Async HTTP client toward the BE (separate LAN machine, backend/api/routes.py).

Real BE contract (mounted at /api AND at root):
  GET  {base}/health | {base}/api/health   -> {status, restaurant, llm_provider, ...}
  POST {base}/api/chat        {message, session_id, customer_id, client_type} -> {reply, ...}
  POST {base}/api/chat/stream {messages|message, session_id, customer_id, client_type}
                               SSE: `data: {"token": "..."}` ... `data: [DONE]`
                               (BE runs full LangGraph inference, THEN streams word-by-word)
  GET  {base}/api/availability?date=YYYY-MM-DD&time=HH:MM&party_size=N|guests=N
  POST {base}/api/reservations              {date,time,guests|party_size,customer_id|name,...}
  GET  {base}/api/reservations/{booking_code}
  PATCH|PUT {base}/api/reservations/{booking_code}
  DELETE {base}/api/reservations/{booking_code}
  GET  {base}/api/menu[?category&allergen_free&is_vegetarian&is_vegan&is_gluten_free]
  GET  {base}/api/info[?key=address|opening_hours|phone|parking]

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
        """Create a reservation (BE maps name -> anonymous customer_id)."""
        log.info("create_reservation date=%s time=%s party=%d name=%s", date, time, party_size, scrub_pii(name))
        return await self._request(
            "POST", "/api/reservations",
            content=json.dumps({"date": date, "time": time, "party_size": party_size, "name": name}),
        )

    async def get_reservation(self, booking_code: str) -> Any:
        """Fetch a reservation by its booking code (e.g. RES-9A8B2C)."""
        return await self._request("GET", f"/api/reservations/{booking_code}")

    async def modify_reservation(
        self,
        booking_code: str,
        new_date: str | None = None,
        new_time: str | None = None,
        new_party_size: int | None = None,
    ) -> Any:
        """Modify date/time/party of a reservation by booking code."""
        body: dict[str, Any] = {}
        if new_date is not None:
            body["new_date"] = new_date
        if new_time is not None:
            body["new_time"] = new_time
        if new_party_size is not None:
            body["new_guests"] = new_party_size
        return await self._request("PATCH", f"/api/reservations/{booking_code}", content=json.dumps(body))

    async def cancel_reservation(self, booking_code: str) -> Any:
        """Cancel a reservation by booking code."""
        return await self._request("DELETE", f"/api/reservations/{booking_code}")

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        timeout_s: float = 30.0,
        session_id: str = "voice_sess",
        customer_id: str = "anon_voice",
        client_type: str = "voice",
    ) -> AsyncIterator[str]:
        """Yield LLM tokens from the BE SSE stream with auto-reconnect (1 retry).

        Sends BE-native session/customer/client fields so LangGraph memory works
        across turns. BE streams ``data: {"token": "..."}`` lines terminated by
        ``data: [DONE]``.
        """
        payload = {
            "messages": [{"role": m["role"], "content": scrub_pii(m["content"])} for m in messages],
            "stream": True,
            "session_id": session_id,
            "customer_id": customer_id,
            "client_type": client_type,
        }
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

    async def chat(
        self,
        message: str,
        session_id: str = "voice_v2",
        customer_id: str = "anon_voice",
        client_type: str = "voice",
    ) -> dict[str, Any]:
        """Non-streaming chat (POST /api/chat), uguale a chat/app.py.

        Usata dalla v2 on-demand: una risposta completa per una domanda completa.
        """
        payload = {
            "message": scrub_pii(message),
            "session_id": session_id,
            "customer_id": customer_id,
            "client_type": client_type,
        }
        result = await self._request("POST", "/api/chat", content=json.dumps(payload))
        if not isinstance(result, dict) or "reply" not in result:
            raise BackendError(f"BE /api/chat: risposta inattesa: {result!r:.200}")
        return result

    async def aclose(self) -> None:
        """Close underlying HTTP connections."""
        await self._client.aclose()
