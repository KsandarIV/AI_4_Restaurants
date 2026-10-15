"""Optional v2 transport: ride on the running CHAT service instead of the BE.

``chat/api.py`` (port 8002) already implements the whole text conversation -
registration, anonymisation, BE call, placeholder restore. With
``CHAT_SERVICE_URL=http://<chat-host>:8002`` the v2 voice mode becomes a pure
speech wrapper around it: STT -> ``POST /chat/message`` -> TTS, and the customer
never sees that a chat bot is working underneath.

Off by default: the project brief says CHAT and VOICE talk to the BE only. Use it
when you want the voice bot to behave *exactly* like the deployed chat bot.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .backend import BackendError
from .interfaces import AbstractLLMOrchestrator, ChatMessage
from .logging_json import get_logger
from .messages import normalize_language, say

log = get_logger("chat_service")


class ChatServiceOrchestrator(AbstractLLMOrchestrator):
    """Same interface as :class:`BackendOrchestrator`, backed by ``chat/api.py``."""

    def __init__(
        self,
        base_url: str,
        language: str = "it",
        timeout_s: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._language = normalize_language(language)
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_s, connect=5.0),
            transport=transport,
        )
        self.session_id = ""
        self.phase = "registration"
        self.history: list[ChatMessage] = []
        self._opening = ""

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = await self._client.post(path, json=body)
        except httpx.TimeoutException as exc:
            raise BackendError("chat service timeout", kind="timeout") from exc
        except httpx.TransportError as exc:
            raise BackendError(f"chat service unreachable: {exc}", kind="unreachable") from exc
        if resp.status_code >= 400:
            raise BackendError(f"chat service {resp.status_code}", status=resp.status_code)
        data = resp.json()
        if not isinstance(data, dict) or "reply" not in data:
            raise BackendError("chat service: unexpected response", kind="format")
        return data

    async def opening(self) -> str:
        """Open a chat-service session; its first message asks for name and phone."""
        try:
            data = await self._post("/chat/session", {})
        except BackendError as exc:
            return self._apology(exc)
        self.session_id = str(data.get("session_id", f"voice_{uuid.uuid4().hex[:8]}"))
        self.phase = str(data.get("phase", "registration"))
        self._opening = str(data["reply"])
        return self._opening

    async def reply(self, user_text: str) -> str:
        """Forward one utterance to the chat service and return its reply."""
        text = user_text.strip()
        if not text:
            return say(self._language, "didnt_hear")
        if not self.session_id:
            await self.opening()
        try:
            data = await self._post("/chat/message", {"session_id": self.session_id, "text": text})
        except BackendError as exc:
            if exc.status == 404:  # chat service restarted: its sessions live in memory
                self.session_id = ""
            return self._apology(exc)
        self.phase = str(data.get("phase", self.phase))
        return str(data["reply"])

    async def stream_reply(self, user_text: str) -> AsyncIterator[str]:
        """The chat service is not streaming: yield the whole reply at once."""
        yield await self.reply(user_text)

    def reset(self) -> None:
        """Forget the session: the next ``opening()`` starts a new one."""
        self.session_id = ""
        self.phase = "registration"
        self.history = []

    async def aclose(self) -> None:
        """Close the HTTP connection."""
        await self._client.aclose()

    def _apology(self, exc: BackendError) -> str:
        if exc.kind == "unreachable":
            return say(self._language, "err_unreachable")
        if exc.kind == "timeout":
            return say(self._language, "err_slow")
        return say(self._language, "err_server")
