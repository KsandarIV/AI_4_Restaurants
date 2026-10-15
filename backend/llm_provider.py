import json
import logging
import re
from typing import Any, List, Optional
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


def get_llm(provider: Optional[str] = None) -> BaseChatModel:
    """
    Factory function to retrieve the configured ChatModel.
    Defaults to local Ollama. Can be set to 'mock' via settings or parameter.
    """
    selected_provider = provider or settings.LLM_PROVIDER

    if selected_provider == "mock":
        logger.info("Using MockChatModel (offline/test mode)")
        return MockChatModel()

    logger.info(
        f"Using local ChatOllama with model='{settings.OLLAMA_MODEL}' at {settings.OLLAMA_BASE_URL}"
    )
    options = {}
    if settings.OLLAMA_REASONING is not None:
        options["reasoning"] = settings.OLLAMA_REASONING
    return ChatOllama(
        model=settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=settings.LLM_TEMPERATURE,
        client_kwargs={"timeout": settings.OLLAMA_TIMEOUT_S},
        **options
    )
