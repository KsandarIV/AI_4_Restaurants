import logging
from typing import Optional, Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver

from backend.graph.state import AgentState
from backend.graph.tools import ALL_TOOLS
from backend.graph.prompts import get_system_prompt
from backend.llm_provider import get_llm

logger = logging.getLogger(__name__)

def create_agent_node(llm):
    """Factory creating the agent decision node with bound tools."""
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    def agent_node(state: AgentState) -> Dict[str, Any]:
        messages = list(state.get("messages", []))

        # Check if SystemMessage is already the first message
        if not messages or not isinstance(messages[0], SystemMessage):
            sys_msg = SystemMessage(content=get_system_prompt())
            messages = [sys_msg] + messages

        # Add context about anonymized customer_id if present
        customer_id = state.get("customer_id")
        client_type = state.get("client_type", "chat")

        # Invoke model
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    return agent_node

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

    memory = checkpointer if checkpointer is not None else MemorySaver()
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
