import logging
import sqlite3
from typing import Optional, Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.sqlite import SqliteSaver

from backend.config import settings
from backend.graph.state import AgentState
from backend.graph.tools import ALL_TOOLS
from backend.graph.prompts import get_system_prompt
from backend.llm_provider import get_llm

logger = logging.getLogger(__name__)

# Tools that act on behalf of a customer: their customer_id is forced from the session state
CUSTOMER_TOOLS = {"create_reservation", "get_reservation", "modify_reservation", "cancel_reservation"}

def create_agent_node(llm):
    """Factory creating the agent decision node with bound tools, custom prompt per client_type, and customer_id."""
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    def agent_node(state: AgentState) -> Dict[str, Any]:
        messages = list(state.get("messages", []))
        customer_id = state.get("customer_id") or "anon_client"
        client_type = state.get("client_type") or "chat"

        # Dynamically generate prompt tailored to client_type ("voice" vs "chat") and customer_id
        sys_prompt = get_system_prompt(
            client_type=client_type,
            customer_id=customer_id
        )

        # Update or prepend SystemMessage
        if messages and isinstance(messages[0], SystemMessage):
            messages[0] = SystemMessage(content=sys_prompt)
        else:
            messages = [SystemMessage(content=sys_prompt)] + messages

        # Invoke model
        response = llm_with_tools.invoke(messages)

        # The customer_id always comes from the session state, never from the LLM: even if the model
        # (or a prompt injection) names another customer, the tools act on behalf of the real one.
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                if tc.get("name") in CUSTOMER_TOOLS:
                    tc.setdefault("args", {})["customer_id"] = customer_id

        return {"messages": [response]}

    return agent_node

def get_sqlite_checkpointer() -> SqliteSaver:
    """Create persistent SQLite checkpointer for LangGraph conversation threads."""
    conn = sqlite3.connect(str(settings.CHECKPOINTS_DB_PATH), check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver

def build_graph(llm=None, checkpointer=None):
    """Build and compile the LangGraph workflow."""
    if llm is None:
        llm = get_llm()

    workflow = StateGraph(AgentState)

    # Define nodes
    workflow.add_node("agent", create_agent_node(llm))
    workflow.add_node("tools", ToolNode(ALL_TOOLS))

    # Define edges
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", tools_condition)
    workflow.add_edge("tools", "agent")

    memory = checkpointer if checkpointer is not None else get_sqlite_checkpointer()
    app = workflow.compile(checkpointer=memory)
    return app

# Singleton default graph
_default_app = None

def get_graph_app():
    global _default_app
    if _default_app is None:
        _default_app = build_graph()
    return _default_app

def process_message(
    message: str,
    session_id: str,
    customer_id: Optional[str] = None,
    client_type: str = "chat",
    app = None
) -> Dict[str, Any]:
    """
    Main helper function to interact with the LangGraph conversational backend.
    """
    graph_app = app or get_graph_app()
    cid = customer_id or f"anon_{session_id}"

    config = {"configurable": {"thread_id": session_id}}

    input_state = {
        "messages": [HumanMessage(content=message)],
        "session_id": session_id,
        "customer_id": cid,
        "client_type": client_type,
        "metadata": {}
    }

    result = graph_app.invoke(input_state, config=config)

    # Extract final AIMessage content
    final_messages = result.get("messages", [])
    reply_text = ""
    for msg in reversed(final_messages):
        if isinstance(msg, AIMessage) and msg.content:
            reply_text = str(msg.content)
            break

    return {
        "reply": reply_text,
        "session_id": session_id,
        "customer_id": cid,
        "client_type": client_type
    }
