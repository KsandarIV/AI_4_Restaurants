"""The voice bot's brain: the chat bot's conversation, spoken.

It reproduces ``chat/api.py`` step by step, so a customer gets the same behaviour on
the phone as in the chat window:

  1. CHAT phase - the call opens with a short welcome; every utterance goes
     anonymise -> BE (``/api/chat`` or the SSE stream) -> restore placeholders -> TTS.
  2. REGISTRATION phase - entered only when the caller talks about booking (menu and
     information never need it): ask name + phone, read them back, confirm, then
     ``POST /api/customers`` -> anonymous ``customer_id``. The LLM never takes part and
     never sees these data. The request that triggered it is kept and sent to the BE
     (anonymised) right after the registration, so the caller does not repeat it.

There are NO local intent shortcuts (no regex "menu"/"booking" detection, no hard-coded
dates): the BE's LangGraph agent decides everything, including the yes/no confirmation of
bookings, allergy answers and registration checks. The voice bot only adds ears and a mouth.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import uuid
from collections.abc import AsyncIterator
from enum import Enum
from typing import Any

from .anonymizer import Anonymizer
from .backend import BackendClient, BackendError
from .contacts import RegistrationDialog, is_plain_no, is_plain_yes, wants_booking
from .interfaces import AbstractLLMOrchestrator, ChatMessage
from .logging_json import get_logger
from .messages import normalize_language, say
from .prompts import build_system_prompt
from .toolguard import NUDGE, first_sentence_done, leaks_tool_talk
from .spoken import spoken_area, spoken_date, spoken_location, spoken_number, spoken_time

log = get_logger("orchestrator")

# Every unregistered caller shares this id: the BE writes the customer id into the LLM's system prompt, so a
# different id per call would make the LLM re-read its whole prompt (about a minute on a weak CPU) at every call.
# It identifies nobody: an anonymous id cannot book, change or cancel.
ANON_CUSTOMER_ID = "anon_voice"

_BOOKING_CODE = re.compile(r"\bRES-[A-Z0-9]{4,10}\b")


# The caller named a room: only then the pop-up shows the room (otherwise the BE just picked one).
_AREA_WORDS = re.compile(
    r"\b(?:terrazza|giardino|sala|interno|interna|dentro|fuori|esterno|all'aperto|veranda|"
    r"terrace|garden|indoors?|outdoors?|inside|outside)\b",
    re.I,
)


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
        max_exchanges: int = 20,
        max_resets: int = 3,
    ) -> None:
        self._backend = backend
        self._system = build_system_prompt(system_prompt)
        self._max_history = max_history
        self._language = normalize_language(language)
        self._require_registration = require_registration
        self._use_ner = use_ner
        self._max_exchanges = max_exchanges
        self._max_resets = max_resets
        self.history: list[ChatMessage] = []
        self._start()

    # ---------------- state ----------------

    def _start(self) -> None:
        self.session_id = f"voice_{uuid.uuid4().hex[:8]}"
        # Replaced by the BE's id once the customer is registered (like chat/api.py).
        self.customer_id = ANON_CUSTOMER_ID
        self.anonymizer = Anonymizer(use_model=self._use_ner)
        self.dialog = RegistrationDialog(self._language)
        self.phase = Phase.CHAT  # registration starts only when the caller wants to book
        self._pending: str | None = None  # the booking request that triggered the registration
        self._replay: str | None = None  # ...ready to be sent to the BE once registered
        self._area_said = False  # the caller asked for a room (terrazza, giardino...) in this booking
        self._exchanges = 0  # BE turns in the current BE session (= the LLM's context grows with them)
        self._resets = 0  # times the context was refreshed without reaching a booking
        self.ended = False  # the call must be closed after the last sentence
        self.history = [ChatMessage(role="system", content=self._system)]
        self._reported: dict[str, tuple[Any, ...]] = {}  # booking code -> details already read aloud
        self._awaiting_final: str | None = None  # code waiting for the caller's last "yes"

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
        """First thing said on the call: a short welcome, nothing is asked yet."""
        text = say(self._language, "welcome_chat")
        self._remember("assistant", text)
        return text

    async def reply(self, user_text: str) -> str:
        """One complete reply through ``POST /api/chat`` (on-demand v2 mode)."""
        local = await self._local_turn(user_text)
        if local is not None:
            replay = self._take_replay()
            return f"{local} {await self._backend_reply(replay)}" if replay else local
        return await self._backend_reply(user_text)

    async def _backend_reply(self, user_text: str) -> str:
        self._exchanges += 1
        anonymized = await self._anonymize(user_text)
        try:
            text = ""
            for attempt in (0, 1):  # a reply that talks about tools is dropped and asked again, once
                data = await self._backend.chat(
                    anonymized if attempt == 0 else anonymized + NUDGE, self.session_id, self.customer_id
                )
                text = self.anonymizer.restore(str(data["reply"]))
                if not leaks_tool_talk(text):
                    break
                log.warning("tool talk in the reply, attempt=%d", attempt + 1)
            else:
                text = say(self._language, "retry_request")
            report = await self._final_report(text)
            if report:
                text = f"{text} {report}"
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
            replay = self._take_replay()
            if replay:
                yield " "
                async for piece in self._backend_stream(replay):
                    yield piece
            return
        async for piece in self._backend_stream(user_text):
            yield piece

    async def _backend_stream(self, user_text: str) -> AsyncIterator[str]:
        self._exchanges += 1
        anonymized = await self._anonymize(user_text)
        spoken: list[str] = []
        try:
            for attempt in (0, 1):  # a reply that talks about tools is dropped and asked again, once
                restorer = self.anonymizer.stream_restorer()
                head: list[str] = []  # the start of the reply is held back until it is known to be clean
                vetted = leaked = False
                message = anonymized if attempt == 0 else anonymized + NUDGE
                stream = self._backend.stream_chat(
                    message, self.session_id, self.customer_id, system_prompt=self._system
                )
                try:
                    async for token in stream:
                        text = restorer.feed(token)
                        if not text:
                            continue
                        if vetted:
                            spoken.append(text)
                            yield text
                            continue
                        head.append(text)
                        joined = "".join(head)
                        if first_sentence_done(joined):
                            if leaks_tool_talk(joined):
                                leaked = True
                                break
                            vetted = True
                            for piece in head:  # release the held-back start, token by token
                                spoken.append(piece)
                                yield piece
                finally:
                    closer = getattr(stream, "aclose", None)
                    if closer is not None:
                        with contextlib.suppress(Exception):
                            await closer()
                if not leaked:
                    tail = restorer.flush()
                    if vetted:
                        if tail:
                            spoken.append(tail)
                            yield tail
                    else:  # a short reply: judged as a whole
                        joined = "".join(head) + tail
                        if joined and leaks_tool_talk(joined):
                            leaked = True
                        elif joined:
                            for piece in [*head, tail] if tail else head:
                                spoken.append(piece)
                                yield piece
                if not leaked:
                    break
                log.warning("tool talk in the reply, attempt=%d", attempt + 1)
            else:
                fallback = say(self._language, "retry_request")
                spoken.append(fallback)
                yield fallback
            if not spoken:  # the BE answered with an empty stream
                raise BackendError("empty reply", kind="format")
            report = await self._final_report("".join(spoken))
            if report:  # the closing summary, spoken right after the BE's own answer
                spoken.append(f" {report}")
                yield f" {report}"
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
        if self.ended:
            return ""  # the call is closing: nothing more is processed
        if not text:
            return say(self._language, "didnt_hear")
        if self.phase is Phase.CHAT and _AREA_WORDS.search(text):
            self._area_said = True
        if (
            self.phase is Phase.CHAT and self._require_registration and not self.registered
            and wants_booking(text)
        ):  # the caller wants to book: only now name and phone are needed
            self._pending = text
            self.phase = Phase.REGISTRATION
            self.dialog = RegistrationDialog(self._language)
            self._remember("user", "(booking request)")  # the words themselves wait for the registration
            reply = self.dialog.opening()
            self._remember("assistant", reply)
            return reply
        if self.phase is Phase.REGISTRATION:
            self._remember("user", "(registration data)")  # never keep contact data in history
            reply = await self._registration_step(text)
            self._remember("assistant", reply)
            return reply
        self._remember("user", text)
        if self._awaiting_final is not None:  # the caller's answer to "is everything correct?"
            self._awaiting_final = None
            who = self._who()
            if is_plain_yes(text):
                await self._emit_event({"event": "reservation_confirmed"})  # the page closes its pop-up
                self._fresh_session()  # goal reached: the next request starts with an empty LLM context
                reply = say(self._language, "final_ok", who=who)
            elif is_plain_no(text):
                reply = say(self._language, "final_no")
            else:  # a correction or a new request: the BE agent handles it
                return self._rotate_if_full()
            self._remember("assistant", reply)
            return reply
        return self._rotate_if_full()

    def _fresh_session(self) -> None:
        """A new BE session: the LLM starts again with an empty context (the customer stays the same)."""
        self.session_id = f"voice_{uuid.uuid4().hex[:8]}"
        self._exchanges = 0
        self._awaiting_final = None
        self.history = [self.history[0]]

    def _rotate_if_full(self) -> str | None:
        """When the LLM's context is full: refresh it with a spoken recap, or end the call.

        Returns the sentence to say, or None while there is still room (the BE then answers).
        The customer stays registered, so nobody has to repeat name or phone.
        """
        if self._exchanges < self._max_exchanges:
            return None
        self._resets += 1
        lang = self._language
        first = (self.dialog.name or "").split(" ")[0] if self.registered else ""
        call = f" {first}, " if first else ", "
        if self._resets > self._max_resets:
            self.ended = True
            reply = say(lang, "context_end", call=call)
        else:
            self._fresh_session()
            reply = say(lang, "context_reset", call=call)
            if self._resets == self._max_resets:
                reply += " " + say(lang, "context_warn")
        log.info("context full: refresh #%d ended=%s", self._resets, self.ended)
        self._remember("assistant", reply)
        return reply

    def _take_replay(self) -> str | None:
        """The booking request to send to the BE now (once), or None."""
        replay, self._replay = self._replay, None
        if replay:
            self._remember("user", replay)
        return replay

    def _who(self) -> str:
        """' for Mario Rossi' - spoken locally, the name never goes to the BE."""
        name = self.dialog.name if self.registered else None
        return say(self._language, "who", name=name) if name else ""

    async def _emit_event(self, payload: dict[str, str]) -> None:
        if self.on_event is not None:
            try:
                await self.on_event(payload)
            except Exception as exc:  # noqa: BLE001 - the UI must never break the call
                log.warning("event hook failed: %r", exc)

    async def _final_report(self, reply: str) -> str:
        """Read back what really happened, from the BE's data, when the reply mentions a booking.

        Not the LLM's words: the booking is fetched with ``GET /api/reservations/{code}`` (owner
        only) and described by code, then the caller is asked for a last yes. Returns "" when
        there is nothing new to report or the lookup fails (silence is better than a wrong report).
        """
        if not self.registered:
            return ""
        codes = _BOOKING_CODE.findall(reply.upper())
        if not codes:
            return ""
        code = codes[-1]
        try:
            res = await self._backend.get_reservation(code, self.customer_id)
        except BackendError as exc:
            log.info("no report for %s: kind=%s status=%s", code, exc.kind, exc.status)
            return ""
        status = str(res.get("status") or "").upper()
        details = (status, res.get("date"), res.get("time"), res.get("guests_count"),
                   res.get("table_number"))
        if self._reported.get(code) == details:
            return ""  # same state already read aloud (e.g. the caller asked for the code again)
        known = code in self._reported
        self._reported[code] = details
        await self._emit_event({
            "event": "reservation", "code": code, "status": status,
            "date": str(res.get("date") or ""), "time": str(res.get("time") or ""),
            "guests": str(res.get("guests_count") or ""), "customer_id": self.customer_id,
            "table": str(res.get("table_number") or ""), "location": str(res.get("table_location") or ""),
            # only for the caller's own page (same WebSocket): their name, and the room only if they asked for it
            "name": self.dialog.name or "",
            "area": spoken_area(res.get("table_location"), self._language) if self._area_said else "",
        })
        self._area_said = False
        self._resets = 0  # a booking was reached: the context counters start over
        lang, who = self._language, self._who()
        if status == "CANCELLED":
            self._awaiting_final = None
            return say(lang, "report_cancelled", code=code, who=who)
        guests = int(res.get("guests_count") or 0)
        party = say(lang, "party_one") if guests == 1 else say(lang, "party_many", n=spoken_number(guests, lang))
        where = spoken_location(res.get("table_location"), lang)
        table = say(lang, "table_part", n=spoken_number(int(res["table_number"]), lang)) if res.get("table_number") else ""
        self._awaiting_final = code
        return say(
            lang, "report_updated" if known else "report_confirmed",
            who=who, party=party, date=spoken_date(str(res.get("date") or ""), lang),
            time=spoken_time(str(res.get("time") or ""), lang), where=f" {where}" if where else "",
            table=table, code=code,
        )

    async def _registration_step(self, text: str) -> str:
        """One step of the registration dialogue (mirrors ``gestisci_registrazione``)."""
        reply, action = self.dialog.handle(text)
        if action == "register":
            try:
                self.customer_id = await self._backend.register_customer(
                    self.dialog.name or "", self.dialog.phone or ""
                )
                self.phase = Phase.CHAT
                self._replay, self._pending = self._pending, None
                log.info("customer registered id=%s", self.customer_id)
                await self._emit_event({"event": "registered", "customer_id": self.customer_id})
                return say(self._language, "registered", name=self.dialog.name or "")
            except BackendError as exc:
                self.dialog.retry_confirmation()  # data is kept: "yes" again retries
                return say(
                    self._language, "register_failed", error=self._error_text(exc, registration=True)
                )
        if action == "give_up":
            self.phase = Phase.CHAT  # carry on with the anonymous customer id
            self._pending = None
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
