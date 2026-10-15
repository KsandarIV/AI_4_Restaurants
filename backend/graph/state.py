from typing import Annotated, Sequence, Optional, Dict, Any
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    session_id: Optional[str]
    customer_id: Optional[str]
    client_type: Optional[str]  # "chat" or "voice"
    metadata: Optional[Dict[str, Any]]
    # Booking/modification/cancellation proposed by the LLM and waiting for the customer's "yes":
    # {"tool": "create_reservation", "args": {...}}. It is executed by code, never by the LLM.
    pending_action: Optional[Dict[str, Any]]
