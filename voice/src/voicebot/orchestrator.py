"""The voice bot's brain: the chat bot's conversation, spoken.

It reproduces ``chat/api.py`` step by step, so a customer gets the same behaviour on
the phone as in the chat window:

  1. REGISTRATION phase - ask name + phone in one utterance, read them back, confirm,
     then ``POST /api/customers`` -> anonymous ``customer_id``. The LLM never takes part
     and never sees these data.
  2. CHAT phase - every utterance goes  anonymise -> BE (``/api/chat`` or the SSE stream)
     -> restore placeholders -> text for the TTS.

There are NO local intent shortcuts (no regex "menu"/"booking" detection, no hard-coded
dates): the BE's LangGraph agent decides everything, including the yes/no confirmation of
bookings, allergy answers and registration checks. The voice bot only adds ears and a mouth.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from enum import Enum

from .anonymizer import Anonymizer
from .backend import BackendClient, BackendError
from .contacts import RegistrationDialog
from .interfaces import AbstractLLMOrchestrator, ChatMessage
from .logging_json import get_logger
from .messages import normalize_language, say
from .prompts import build_system_prompt

log = get_logger("orchestrator")


class Phase(str, Enum):
    """Where the conversation is (same two phases as the chat bot)."""

    REGISTRATION = "registration"
    CHAT = "chat"


class BackendOrchestrator(AbstractLLMOrchestrator):
    """One caller's conversation with the BE, with the chat bot's rules."""

    def __init__(
        self,
        backend: BackendClient,
        system_prompt: str = "",
        max_history: int = 12,
        language: str = "it",
        require_registration: bool = True,
        use_ner: bool | None = None,
    ) -> None:
        self._backend = backend
        self._system = build_system_prompt(system_prompt)
        self._max_history = max_history
        self._language = normalize_language(language)
        self._require_registration = require_registration
        self._use_ner = use_ner
        self.history: list[ChatMessage] = []
        self._start()

    # ---------------- state ----------------

    def _start(self) -> None:
        self.session_id = f"voice_{uuid.uuid4().hex[:8]}"
        # Replaced by the BE's id once the customer is registered (like chat/api.py).
        self.customer_id = f"anon_{uuid.uuid4().hex[:6]}"
        self.anonymizer = Anonymizer(use_model=self._use_ner)
        self.dialog = RegistrationDialog(self._language)
        self.phase = Phase.REGISTRATION if self._require_registration else Phase.CHAT
        self.history = [ChatMessage(role="system", content=self._system)]

    def reset(self) -> None:
        """Start a brand-new conversation: new session, new customer, empty placeholder map."""
        self._start()

    @property
    def registered(self) -> bool:
        """True once the BE has issued a real (non-anonymous) customer id."""
        return not self.customer_id.startswith("anon_")

    def _remember(self, role: str, content: str) -> None:
        self.history.append(ChatMessage(role=role, content=content))  # type: ignore[arg-type]
        if len(self.history) > self._max_history + 1:  # keep the system prompt + last N
            self.history = [self.history[0]] + self.history[-self._max_history :]

    # ---------------- public API ----------------

    async def opening(self) -> str:
        """First thing said on the call: ask for contact data, or welcome."""
        text = (
            self.dialog.opening()
            if self.phase is Phase.REGISTRATION
            else say(self._language, "welcome_chat")
        )
        self._remember("assistant", text)
        return text

    async def reply(self, user_text: str) -> str:
        """One complete reply through ``POST /api/chat`` (on-demand v2 mode)."""
        local = await self._local_turn(user_text)
        if local is not None:
            return local
        anonymized = await self._anonymize(user_text)
        try:
            data = await self._backend.chat(anonymized, self.session_id, self.customer_id)
            text = self.anonymizer.restore(str(data["reply"]))
        except BackendError as exc:
            log.error("chat failed kind=%s status=%s", exc.kind, exc.status)
            text = self._error_text(exc)
        self._remember("assistant", text)
        return text

    async def stream_reply(self, user_text: str) -> AsyncIterator[str]:
        """Yield the reply token by token through the SSE endpoint (live v1 mode)."""
        local = await self._local_turn(user_text)
        if local is not None:
            yield local
            return
        anonymized = await self._anonymize(user_text)
        restorer = self.anonymizer.stream_restorer()
        spoken: list[str] = []
        try:
            async for token in self._backend.stream_chat(
                anonymized, self.session_id, self.customer_id, system_prompt=self._system
            ):
                text = restorer.feed(token)
                if text:
                    spoken.append(text)
                    yield text
            tail = restorer.flush()
            if tail:
                spoken.append(tail)
                yield tail
            if not spoken:  # the BE answered with an empty stream
                raise BackendError("empty reply", kind="format")
        except BackendError as exc:
            log.error("stream failed kind=%s status=%s", exc.kind, exc.status)
            apology = self._error_text(exc)
            spoken.append(apology)
            yield apology
        finally:
            if spoken:
                self._remember("assistant", "".join(spoken))

    async def aclose(self) -> None:
        """Close the BE connection."""
        await self._backend.aclose()

    # ---------------- internals ----------------

    async def _anonymize(self, text: str) -> str:
        # The NER model can take tens of ms: keep it off the event loop.
        return await asyncio.to_thread(self.anonymizer.anonymize, text)

    async def _local_turn(self, user_text: str) -> str | None:
        """Handle turns that never reach the LLM. Returns None for a normal CHAT turn."""
        text = user_text.strip()
        if not text:
            return say(self._language, "didnt_hear")
        if self.phase is Phase.REGISTRATION:
            self._remember("user", "(registration data)")  # never keep contact data in history
            reply = await self._registration_step(text)
            self._remember("assistant", reply)
            return reply
        self._remember("user", text)
        return None

    async def _registration_step(self, text: str) -> str:
        """One step of the registration dialogue (mirrors ``gestisci_registrazione``)."""
        reply, action = self.dialog.handle(text)
        if action == "register":
            try:
                self.customer_id = await self._backend.register_customer(
                    self.dialog.name or "", self.dialog.phone or ""
                )
                self.phase = Phase.CHAT
                log.info("customer registered id=%s", self.customer_id)
                return say(self._language, "registered", name=self.dialog.name or "")
            except BackendError as exc:
                self.dialog.retry_confirmation()  # data is kept: "yes" again retries
                return say(
                    self._language, "register_failed", error=self._error_text(exc, registration=True)
                )
        if action == "give_up":
            self.phase = Phase.CHAT  # carry on with the anonymous customer id
        return reply

    def _error_text(self, exc: BackendError, registration: bool = False) -> str:
        """A short, speakable apology: never technical details, never a stack trace."""
        lang = self._language
        if exc.kind == "unreachable":
            return say(lang, "err_unreachable")
        if exc.kind == "timeout":
            return say(lang, "err_slow")
        if exc.status == 503:
            return say(lang, "err_llm_down")
        if registration and exc.status in (404, 405):
            return say(lang, "err_registration_unsupported")
        if registration and exc.status is not None and 400 <= exc.status < 500:
            return say(lang, "err_registration_rejected")
        return say(lang, "err_server")
