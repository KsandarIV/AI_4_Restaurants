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
