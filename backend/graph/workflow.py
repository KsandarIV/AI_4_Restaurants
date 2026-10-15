import datetime
import logging
import re
import sqlite3
from typing import Optional, Dict, Any, List, Tuple
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.sqlite import SqliteSaver

from backend.config import settings
from backend.database import crud
from backend.database.connection import SessionLocal
from backend.graph.state import AgentState
from backend.graph.tools import ALL_TOOLS
from backend.graph.prompts import get_system_prompt
from backend.llm_provider import get_llm

logger = logging.getLogger(__name__)

# Tools that act on behalf of a customer: their customer_id is forced from the session state
CUSTOMER_TOOLS = {"create_reservation", "get_reservation", "modify_reservation", "cancel_reservation"}

# Tools that change data. The LLM can only PROPOSE them: the customer must explicitly confirm,
# and the action is then executed by code (see process_message). A weak model that calls
# create_reservation on a greeting or on garbage therefore cannot create phantom bookings.
GATED_TOOLS = {"create_reservation", "modify_reservation", "cancel_reservation"}
TOOLS_BY_NAME = {t.name: t for t in ALL_TOOLS}

_GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
_MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
         "settembre", "ottobre", "novembre", "dicembre"]

# A message counts as a confirmation only if it is made of these words alone ("sì", "ok va bene").
# "sì ma alle 21" is NOT a confirmation: it is a change, and goes back to the LLM.
_CONFIRM_WORDS = {
    "sì", "si", "ok", "okay", "certo", "certamente", "confermo", "conferma", "confermare", "va", "bene",
    "perfetto", "esatto", "assolutamente", "yes", "pure", "prenota", "procedi", "vai", "grazie", "giusto",
    "d", "accordo",
}


def is_confirmation(text: str) -> bool:
    words = re.findall(r"[^\W\d_]+", text.lower())
    return 0 < len(words) <= 4 and all(w in _CONFIRM_WORDS for w in words)


def _data_it(date_str: str) -> str:
    d = datetime.date.fromisoformat(date_str)
    return f"{_GIORNI[d.weekday()]} {d.day} {_MESI[d.month - 1]}"


def _build_proposal(tool: str, args: Dict[str, Any], customer_id: str) -> Tuple[Optional[str], Optional[str]]:
    """Checks a booking/modification/cancellation proposed by the LLM, without changing anything.

    Returns (error, summary): an error text to show to the customer, or the summary to confirm.
    """
    try:
        with SessionLocal() as db:
            if tool == "create_reservation":
                date, time, guests = args.get("date"), args.get("time"), int(args.get("guests"))
                if not date or not time:
                    raise ValueError
                error, _ = crud.validate_reservation_request(db, date, time, guests, customer_id)
                if error:
                    return error, None
                location = args.get("preferred_location") or None
                tables = crud.get_available_tables(db, date, time, guests, preferred_location=location)
                if not tables and location:
                    tables = crud.get_available_tables(db, date, time, guests)
                if not tables:
                    return f"Purtroppo non ci sono tavoli disponibili per {guests} persone {_data_it(date)} alle {time}.", None
                extra = f", sala {location}" if location else ""
                if args.get("special_requests"):
                    extra += f", richieste: {args['special_requests']}"
                return None, (
                    f"Riepilogo: tavolo per {guests} persone {_data_it(date)} alle {time}{extra}. "
                    "Confermi la prenotazione? Rispondi sì per confermare o no per annullare."
                )

            code = str(args.get("booking_code") or "").strip().upper()
            res = crud.get_reservation(db, code, customer_id=customer_id)
            if not res:
                return f"Non trovo nessuna prenotazione con il codice {code or '(mancante)'}.", None
            if res["status"] == "CANCELLED":
                return f"La prenotazione {code} è già stata cancellata.", None
            current = f"{_data_it(res['date'])} alle {res['time']} per {res['guests_count']} persone"

            if tool == "cancel_reservation":
                return None, f"Vuoi cancellare la prenotazione {code} ({current})? Confermi? Rispondi sì o no."

            changes = []
            if args.get("new_date"):
                changes.append(f"nuova data {_data_it(args['new_date'])}")
            if args.get("new_time"):
                changes.append(f"nuovo orario {args['new_time']}")
            if args.get("new_guests"):
                changes.append(f"{int(args['new_guests'])} persone")
            if args.get("new_requests"):
                changes.append(f"richieste: {args['new_requests']}")
            if not changes:
                return f"Cosa vuoi modificare della prenotazione {code} ({current})?", None
            return None, (
                f"Vuoi modificare la prenotazione {code} ({current}): {', '.join(changes)}. "
                "Confermi? Rispondi sì o no."
            )
    except (ValueError, TypeError):
        return "Per procedere mi servono data, orario e numero di persone: me li può indicare?", None


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
        tool_calls = getattr(response, "tool_calls", None) or []

        # The customer_id always comes from the session state, never from the LLM: even if the model
        # (or a prompt injection) names another customer, the tools act on behalf of the real one.
        for tc in tool_calls:
            if tc.get("name") in CUSTOMER_TOOLS:
                tc.setdefault("args", {})["customer_id"] = customer_id

        # Booking, modification and cancellation are not executed here: the customer must confirm first.
        # The LLM's tool call is replaced by a summary written by code (no tool call is left dangling).
        gated = next((tc for tc in tool_calls if tc.get("name") in GATED_TOOLS), None)
        if gated:
            args = {k: v for k, v in (gated.get("args") or {}).items() if k != "customer_id"}
            error, summary = _build_proposal(gated["name"], args, customer_id)
            if error:
                return {"messages": [AIMessage(content=error)], "pending_action": None}
            return {
                "messages": [AIMessage(content=summary)],
                "pending_action": {"tool": gated["name"], "args": args},
            }

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

def _execute_pending(pending: Dict[str, Any], customer_id: str, client_type: str) -> str:
    """Runs the confirmed action through its tool and returns the text for the customer."""
    reply = TOOLS_BY_NAME[pending["tool"]].invoke({**pending["args"], "customer_id": customer_id})
    if client_type == "voice":
        reply = reply.replace("#", "numero ")  # a voice cannot read "#"
    return reply

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
    result_info = {"session_id": session_id, "customer_id": cid, "client_type": client_type}

    # A booking/modification/cancellation is waiting for the customer's answer
    snapshot = graph_app.get_state(config)
    pending = (snapshot.values or {}).get("pending_action") if snapshot else None
    if pending:
        if is_confirmation(message):
            reply = _execute_pending(pending, cid, client_type)
            graph_app.update_state(
                config,
                {"messages": [HumanMessage(content=message), AIMessage(content=reply)], "pending_action": None},
                as_node="agent",
            )
            return {"reply": reply, **result_info}
        # "no", a change ("sì ma alle 21") or any other message: the proposal is dropped and the LLM takes over
        graph_app.update_state(config, {"pending_action": None}, as_node="agent")

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

    return {"reply": reply_text, **result_info}
