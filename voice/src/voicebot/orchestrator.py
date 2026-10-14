"""LLM orchestrator: dialogue state + BE function-calling + token streaming.

The heavy LLM lives on the BE (local model, e.g. Ollama). This orchestrator:
  1. keeps short dialogue history,
  2. detects reservation intents locally (regex, no network),
  3. calls BE tools (availability/reserve/modify/cancel/menu/info) directly for
     low latency, and
  4. otherwise streams the reply token-by-token from the BE chat endpoint so
     the TTS can start speaking before the turn is complete.
"""

from __future__ import annotations

import asyncio
import re
from typing import AsyncIterator

from .backend import BackendClient
from .interfaces import AbstractLLMOrchestrator, ChatMessage
from .logging_json import get_logger

log = get_logger("orchestrator")

_RESERVE = re.compile(r"prenot|tavolo|riserv", re.IGNORECASE)
_MENU = re.compile(r"men[uù]|carta|piatti|mangiare", re.IGNORECASE)
_INFO = re.compile(r"dove|indirizzo|posizione|telefono|contatt|orari|apert", re.IGNORECASE)
_CANCEL = re.compile(r"cancell|annulla|elimina", re.IGNORECASE)
_MODIFY = re.compile(r"modifica|cambia|sposta", re.IGNORECASE)
_PARTY = re.compile(r"(\d{1,2})\s*(person|posti|ospiti|siamo in)")
_TIME = re.compile(r"(\d{1,2})(?:[:.](\d{2}))?\s*(?:alle|ore)?", re.IGNORECASE)


class BackendOrchestrator(AbstractLLMOrchestrator):
    """Orchestrator bound to a BackendClient (streaming LLM on BE)."""

    def __init__(
        self,
        backend: BackendClient,
        system_prompt: str,
        max_history: int = 12,
        token_timeout_s: float = 30.0,
    ) -> None:
        self._backend = backend
        self._system = system_prompt
        self._max_history = max_history
        self._token_timeout = token_timeout_s
        self.history: list[ChatMessage] = [ChatMessage(role="system", content=system_prompt)]

    def reset(self) -> None:
        """Clear history back to the system prompt."""
        sys_msg = self.history[0] if self.history else ChatMessage(role="system", content=self._system)
        self.history = [sys_msg]

    def _push(self, msg: ChatMessage) -> None:
        self.history.append(msg)
        # Keep system + last N turns.
        if len(self.history) > self._max_history + 1:
            self.history = [self.history[0]] + self.history[-self._max_history:]

    async def stream_reply(self, user_text: str) -> AsyncIterator[str]:
        """Yield tokens; fast-path tool calls answer without LLM round-trip."""
        text = user_text.strip()
        if not text:
            yield "Non ho sentito bene, puoi ripetere?"
            return
        self._push(ChatMessage(role="user", content=text))

        shortcut = await self._tool_shortcut(text)
        if shortcut is not None:
            self._push(ChatMessage(role="assistant", content=shortcut))
            yield shortcut
            return

        messages = [{"role": m.role, "content": m.content} for m in self.history]
        full: list[str] = []
        try:
            async def _gen() -> AsyncIterator[str]:
                async for tok in self._backend.stream_chat(messages, timeout_s=self._token_timeout):
                    yield tok

            gen = _gen()
            while True:
                try:
                    token = await asyncio.wait_for(gen.__anext__(), timeout=self._token_timeout)
                except StopAsyncIteration:
                    break
                full.append(token)
                yield token
        except (asyncio.TimeoutError, asyncio.CancelledError):
            log.warning("llm stream interrupted/cancelled")
            raise
        except Exception as exc:
            log.error("llm stream failed: %s", exc)
            fallback = "Mi dispiace, il servizio è momentaneamente non disponibile. Riprova tra poco."
            self._push(ChatMessage(role="assistant", content=fallback))
            yield fallback
            return
        self._push(ChatMessage(role="assistant", content="".join(full)))

    async def _tool_shortcut(self, text: str) -> str | None:
        """Direct BE calls for clear intents (menu/info/availability)."""
        try:
            if _MENU.search(text):
                menu = await self._backend.get_menu()
                return f"Ecco il nostro menu: {menu}" if menu else "Il menu di oggi prevede antipasti, primi, secondi e dolci."
            if _INFO.search(text) and not _RESERVE.search(text):
                info = await self._backend.get_info()
                return f"Ecco le informazioni: {info}" if info else "Ci trovi in centro, aperti tutti i giorni dalle 12 alle 23."
            if _RESERVE.search(text) and not (_CANCEL.search(text) or _MODIFY.search(text)):
                party = _PARTY.search(text)
                time = _TIME.search(text)
                if party and time:
                    hour = time.group(1)
                    minute = time.group(2) or "00"
                    avail = await self._backend.check_availability(
                        date="2026-10-15", time=f"{hour}:{minute}", party_size=int(party.group(1))
                    )
                    return f"Ho verificato la disponibilità: {avail}"
        except Exception as exc:
            log.warning("tool shortcut failed: %s", exc)
        return None
