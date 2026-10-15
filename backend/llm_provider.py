import json
import logging
import re
import threading
import time
from typing import Any, List, Optional, Tuple
import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_ollama import ChatOllama
from backend.config import settings

logger = logging.getLogger(__name__)

class MockChatModel(BaseChatModel):
    """
    Deterministic mock chat model for testing and offline development
    when Ollama local daemon is not running.
    Capable of calling tools or producing conversational responses.
    """
    model_name: str = "mock-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self

    @property
    def _llm_type(self) -> str:
        return "mock-chat-model"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        last_msg = messages[-1].content if messages else ""
        text = str(last_msg).lower()

        # Check for tool response
        if messages and messages[-1].type == "tool":
            tool_content = messages[-1].content
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content=f"Ho elaborato la richiesta. Ecco il risultato: {tool_content}"
                        )
                    )
                ]
            )

        # 1. Menu request
        if "menu" in text or "primi" in text or "piatti" in text:
            category = None
            if "primi" in text:
                category = "Primi"
            elif "secondi" in text:
                category = "Secondi"
            elif "dolci" in text or "dessert" in text:
                category = "Dessert"

            tool_call = {
                "name": "get_menu",
                "args": {"category": category},
                "id": "call_mock_menu_1",
                "type": "tool_call"
            }
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content="",
                            tool_calls=[tool_call]
                        )
                    )
                ]
            )

        # 2. Info request
        if "orari" in text or "aperti" in text or "chiuso" in text:
            tool_call = {
                "name": "get_restaurant_info",
                "args": {"key": "opening_hours"},
                "id": "call_mock_info_1",
                "type": "tool_call"
            }
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content="",
                            tool_calls=[tool_call]
                        )
                    )
                ]
            )
        if "dove" in text or "indirizzo" in text or "posizione" in text or "parcheggio" in text:
            key = "parking" if "parcheggio" in text else "address"
            tool_call = {
                "name": "get_restaurant_info",
                "args": {"key": key},
                "id": "call_mock_info_2",
                "type": "tool_call"
            }
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content="",
                            tool_calls=[tool_call]
                        )
                    )
                ]
            )

        # 3. Cancel reservation
        if "cancella" in text or "annulla" in text:
            match = re.search(r"res-[a-z0-9]+", text)
            code = match.group(0).upper() if match else "RES-UNKNOWN"
            tool_call = {
                "name": "cancel_reservation",
                "args": {"booking_code": code},
                "id": "call_mock_cancel_1",
                "type": "tool_call"
            }
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content="",
                            tool_calls=[tool_call]
                        )
                    )
                ]
            )

        # 4. Modify reservation
        if "modifica" in text:
            match = re.search(r"res-[a-z0-9]+", text)
            code = match.group(0).upper() if match else "RES-UNKNOWN"
            tool_call = {
                "name": "modify_reservation",
                "args": {"booking_code": code, "new_guests": 4},
                "id": "call_mock_mod_1",
                "type": "tool_call"
            }
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content="",
                            tool_calls=[tool_call]
                        )
                    )
                ]
            )

        # 5. Booking table
        if "prenotare" in text or "tavolo" in text:
            # Check if has details
            date_match = re.search(r"\d{4}-\d{2}-\d{2}", text)
            time_match = re.search(r"\d{1,2}:\d{2}", text)
            date = date_match.group(0) if date_match else "2026-10-21"
            time = time_match.group(0) if time_match else "20:30"
            guests = 2
            for word in text.split():
                if word.isdigit():
                    guests = int(word)
                    break

            cid = "anon_client"
            for msg in messages:
                if msg.type == "system" and "customer_id: '" in msg.content:
                    try:
                        cid = msg.content.split("customer_id: '")[1].split("'")[0]
                    except Exception:
                        pass

            tool_call = {
                "name": "create_reservation",
                "args": {
                    "date": date,
                    "time": time,
                    "guests": guests,
                    "customer_id": cid,
                    "special_requests": ""
                },
                "id": "call_mock_book_1",
                "type": "tool_call"
            }
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content="",
                            tool_calls=[tool_call]
                        )
                    )
                ]
            )

        # Default conversational greeting
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="Buongiorno e benvenuto alla Trattoria Bella Napoli! Come posso esserle utile oggi? Posso aiutarla a prenotare un tavolo, consultare il menu, modificare una prenotazione o darle informazioni sul nostro locale."
                    )
                )
            ]
        )


class ModelUnavailable(RuntimeError):
    """Ollama is reachable but none of the wanted models is installed and able to call tools."""


_resolved: Optional[Tuple[str, bool]] = None  # (installed model name, supports thinking), decided once
_resolve_lock = threading.Lock()  # the warm-up thread and the first request must not decide twice


def _candidates() -> List[str]:
    wanted = [m.strip() for m in settings.OLLAMA_MODEL.split(",") if m.strip()] + list(settings.OLLAMA_FALLBACK_MODELS)
    return list(dict.fromkeys(wanted))  # no duplicates, order kept


def _matches(candidate: str, installed: str) -> bool:
    """'llama3.2' matches 'llama3.2:latest'; 'gemma4:12b' matches only that tag."""
    return installed == candidate or (":" not in candidate and installed.split(":")[0] == candidate)


def resolve_ollama_model(force: bool = False) -> Tuple[str, bool]:
    """Chooses the model to use: the first wanted one that is installed and can call tools (needed to book).

    Returns (installed name, supports thinking). The choice is remembered. Raises httpx errors if Ollama is
    down and ModelUnavailable if no suitable model is installed.
    """
    with _resolve_lock:
        return _resolve_locked(force)


def _resolve_locked(force: bool) -> Tuple[str, bool]:
    global _resolved
    if _resolved and not force:
        return _resolved
    base = settings.OLLAMA_BASE_URL.rstrip("/")
    installed = [m["name"] for m in httpx.get(f"{base}/api/tags", timeout=3).json().get("models", [])]
    for candidate in _candidates():
        for name in installed:
            if not _matches(candidate, name):
                continue
            capabilities = httpx.post(f"{base}/api/show", json={"model": name, "name": name}, timeout=5).json().get("capabilities", [])
            if "tools" not in capabilities:
                logger.warning("Il modello %s non supporta gli strumenti: non può prenotare, lo salto.", name)
                continue
            _resolved = (name, "thinking" in capabilities)
            if candidate != _candidates()[0]:
                logger.warning("Modello preferito non disponibile: uso %s.", name)
            logger.info("Modello scelto: %s (thinking supportato: %s)", name, "sì" if _resolved[1] else "no")
            return _resolved
    raise ModelUnavailable(
        f"Nessun modello adatto in Ollama. Cercati: {', '.join(_candidates())}. "
        f"Installati: {', '.join(installed) or 'nessuno'}. Scaricane uno, ad esempio: ollama pull gemma4:12b"
    )


def effective_reasoning(supports_thinking: bool) -> bool:
    """Thinking is OFF unless explicitly requested (and supported by the model)."""
    wanted = settings.OLLAMA_REASONING
    if wanted is None:
        return False
    if wanted and not supports_thinking:
        logger.warning("OLLAMA_REASONING=true ignorato: il modello non supporta il thinking.")
        return False
    return wanted


def warm_up() -> None:
    """Loads the model in memory at startup, so the first customer does not wait 20-40 seconds. Never raises."""
    if settings.LLM_PROVIDER == "mock":
        return
    try:
        started = time.time()
        get_llm().invoke("Rispondi solo con la parola: ok")
        logger.info("Modello pronto in memoria (%.0f s).", time.time() - started)
    except Exception as e:
        logger.warning("Riscaldamento del modello non riuscito (%s). Il primo messaggio sarà lento o fallirà finché Ollama non risponde.", e)


def get_llm(provider: Optional[str] = None) -> BaseChatModel:
    """
    Factory function to retrieve the configured ChatModel.
    Defaults to local Ollama. Can be set to 'mock' via settings or parameter.
    """
    selected_provider = provider or settings.LLM_PROVIDER

    if selected_provider == "mock":
        logger.info("Using MockChatModel (offline/test mode)")
        return MockChatModel()

    model, supports_thinking = resolve_ollama_model()
    return ChatOllama(
        model=model,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=settings.LLM_TEMPERATURE,
        keep_alive=settings.OLLAMA_KEEP_ALIVE,
        reasoning=effective_reasoning(supports_thinking),
        client_kwargs={"timeout": settings.OLLAMA_TIMEOUT_S},
    )
