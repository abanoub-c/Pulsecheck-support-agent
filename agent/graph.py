"""
Pulsecheck support agent — Main LangGraph Execution Graph.

Belongs at: agent/graph.py

Wires the Router, Specialist nodes (Billing, Technical, Refund),
Tool execution nodes, and Escalation handler into a stateful graph
with conditional routing based on classifier confidence, loop guardrails,
and tool-call execution.

Changes in this version:
  * escalate_node uses _text() for message content (list-type content crashed the join),
    puts `escalation_reason` in the interrupt payload (so loop_guard_exceeded is visible),
    rounds confidence to the CRM's 3 decimals, adds request timeouts, and de-duplicates
    on ticket_id + conversation_summary instead of ticket_id alone (None == None matched
    unrelated rows).
  * route_specialist hands off to `dispatch` when more categories are pending, so hybrid
    tickets (billing + technical, ...) run every specialist in the same turn.
  * Specialist nodes are wrapped so each LLM turn leaves an audit record in actions_taken
    (the eval runner, and any reviewer, can then see which specialist ran).
"""
import os
from datetime import datetime, timezone
from typing import Literal

import requests
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt

from agent.nodes.billing import BILLING_TOOLS, billing_node
from agent.nodes.context_manager import context_manager_node
from agent.nodes.dispatch import dispatch_node
from agent.nodes.refund import REFUND_TOOLS, refund_node
from agent.nodes.router import router_node
from agent.nodes.technical import TECHNICAL_TOOLS, technical_node
from agent.state import SupportState


def _text(content) -> str:
    """Message content may be a str or a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b if isinstance(b, str) else str(b.get("text", ""))
            for b in content
            if isinstance(b, (str, dict))
        )
    return "" if content is None else str(content)


# ---------------------------------------------------------------------------
# Tool Execution Nodes
# ---------------------------------------------------------------------------
billing_tools_node = ToolNode(BILLING_TOOLS)
technical_tools_node = ToolNode(TECHNICAL_TOOLS)
refund_tools_node = ToolNode(REFUND_TOOLS)
MAX_SPECIALIST_STEPS = int(os.getenv("MAX_SPECIALIST_STEPS", "8"))


# ---------------------------------------------------------------------------
# Audit wrapper for specialist nodes
# ---------------------------------------------------------------------------
def _audited(name: str, fn):
    """Wrap a specialist so every LLM turn appends a record to actions_taken."""

    def node(state: SupportState) -> dict:
        out = dict(fn(state))
        last = (out.get("messages") or [None])[-1]
        requested = [tc.get("name") for tc in (getattr(last, "tool_calls", None) or [])]
        out["actions_taken"] = list(out.get("actions_taken", [])) + [{
            "node": name,
            "tool": "llm_turn",
            "arguments": {},
            "result": {"tool_calls_requested": requested},
            "success": True,
            "error": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
        return out

    return node


# ---------------------------------------------------------------------------
# Escalation Node
# ---------------------------------------------------------------------------
API_BASE = os.getenv("API_BASE", "http://localhost:8000")


def escalate_node(state: SupportState) -> dict:
    reason = state.get("escalation_reason")
    if reason is None and state.get("turn_count", 0) >= MAX_SPECIALIST_STEPS:
        reason = "loop_guard_exceeded"

    summary = " | ".join(
        _text(m.content) for m in state["messages"][-6:] if getattr(m, "content", None)
    )
    confidence = state.get("confidence")
    payload = {
        "escalation_reason": reason,
        "category": state.get("category"),
        "confidence": confidence,
        "reasoning": " — ".join(p for p in (reason, state.get("classification_reasoning")) if p) or None,
        "proposed_action": state.get("proposed_action"),
        "conversation_summary": summary,
    }

    customer_id = state.get("customer_id")
    ticket_id = state.get("ticket_id")
    escalation_id = None

    # interrupt() re-runs this node from the top on resume, so anything above it must be
    # idempotent: look for the row we already created (same customer, ticket and summary)
    # before POSTing a new one.
    if customer_id:
        try:
            existing = requests.get(
                f"{API_BASE}/escalations",
                params={"status": "pending", "customer_id": customer_id},
                timeout=10,
            )
            if existing.ok:
                match = next(
                    (
                        e for e in existing.json()
                        if e.get("ticket_id") == ticket_id and e.get("conversation_summary") == summary
                    ),
                    None,
                )
                if match:
                    escalation_id = match["escalation_id"]
        except requests.RequestException:
            pass

        if escalation_id is None:
            try:
                resp = requests.post(
                    f"{API_BASE}/escalations",
                    json={
                        "customer_id": customer_id,
                        "category": state.get("category") or "other",
                        "ticket_id": ticket_id,
                        # EscalationCreate.confidence allows at most 3 decimal places.
                        "confidence": round(confidence, 3) if confidence is not None else None,
                        "reasoning": payload["reasoning"],
                        "proposed_action": payload["proposed_action"],
                        "conversation_summary": summary,
                    },
                    timeout=10,
                )
                escalation_id = resp.json().get("escalation_id") if resp.ok else None
            except requests.RequestException:
                escalation_id = None

    decision = interrupt(payload)

    last = state["messages"][-1] if state["messages"] else None
    unanswered = (
        [ToolMessage(content="Not executed: conversation escalated to a human.", tool_call_id=tc["id"])
         for tc in last.tool_calls]
        if isinstance(last, AIMessage) and last.tool_calls else []
    )

    return {
        "escalation_id": escalation_id,
        "resolution_status": "resolved" if decision.get("action") == "approve" else "escalated",
        "pending_categories": [],
        "clarify_attempts": 0,
        "escalation_reason": None,
        "category": None,
        "messages": unanswered + [AIMessage(content=decision.get(
            "customer_message",
            "I have flagged your account for human review. A support specialist will follow up shortly.",
        ))],
    }


# ---------------------------------------------------------------------------
# Conditional Edge Routing Logic
# ---------------------------------------------------------------------------
def route_after_router(state: SupportState) -> Literal["dispatch", "billing", "technical", "refund", "escalate", "__end__"]:
    if state.get("resolution_status") == "escalated":
        return "escalate"
    if state.get("pending_categories"):
        return "dispatch"
    if state.get("category"):
        return state["category"]  # sticky continuation — no reclassification cycle
    return END


def route_after_dispatch(state: SupportState) -> Literal["billing", "technical", "refund", "escalate", "__end__"]:
    if state.get("resolution_status") == "escalated":
        return "escalate"

    category = state.get("category")
    if category == "billing":
        return "billing"
    elif category == "technical":
        return "technical"
    elif category == "refund":
        return "refund"
    return END


def route_specialist(state: SupportState) -> str:
    if state.get("resolution_status") == "escalated":
        return "escalate"

    messages = state.get("messages", [])
    last = messages[-1] if messages else None

    if isinstance(last, AIMessage) and last.tool_calls:
        # A runaway loop can only happen when the specialist keeps asking for tools.
        if state.get("turn_count", 0) >= MAX_SPECIALIST_STEPS:
            return "escalate"
        category = state.get("category")
        if category == "billing":
            return "billing_tools"
        elif category == "technical":
            return "technical_tools"
        elif category == "refund":
            return "refund_tools"

    # This specialist is done. If the router queued more categories (hybrid ticket),
    # hand off to the next specialist instead of ending the turn.
    if state.get("pending_categories"):
        return "dispatch"
    return END


# ---------------------------------------------------------------------------
# Graph Construction & Wiring
# ---------------------------------------------------------------------------
builder = StateGraph(SupportState)

# 1. Nodes
builder.add_node("context_manager", context_manager_node)
builder.add_node("router", router_node)
builder.add_node("billing", _audited("billing", billing_node))
builder.add_node("technical", _audited("technical", technical_node))
builder.add_node("refund", _audited("refund", refund_node))
builder.add_node("billing_tools", billing_tools_node)
builder.add_node("technical_tools", technical_tools_node)
builder.add_node("refund_tools", refund_tools_node)
builder.add_node("escalate", escalate_node)
builder.add_node("dispatch", dispatch_node)

# 2. Entry point
builder.add_edge(START, "context_manager")
builder.add_edge("context_manager", "router")

# 3. Conditional routing
builder.add_conditional_edges(
    "router",
    route_after_router,
    {"dispatch": "dispatch", "escalate": "escalate", "billing": "billing",
     "technical": "technical", "refund": "refund", END: END},
)
builder.add_conditional_edges(
    "dispatch",
    route_after_dispatch,
    {"billing": "billing", "technical": "technical", "refund": "refund",
     "escalate": "escalate", END: END},
)
builder.add_conditional_edges(
    "billing", route_specialist,
    {"billing_tools": "billing_tools", "escalate": "escalate", "dispatch": "dispatch", END: END},
)
builder.add_conditional_edges(
    "technical", route_specialist,
    {"technical_tools": "technical_tools", "escalate": "escalate", "dispatch": "dispatch", END: END},
)
builder.add_conditional_edges(
    "refund", route_specialist,
    {"refund_tools": "refund_tools", "escalate": "escalate", "dispatch": "dispatch", END: END},
)

# 4. Tool-to-specialist feedback loops
builder.add_edge("billing_tools", "billing")
builder.add_edge("technical_tools", "technical")
builder.add_edge("refund_tools", "refund")

# 5. Escalation endpoint
builder.add_edge("escalate", END)

# Compile (langgraph dev supplies its own persistence; the eval runner and
# service.py compile their own copy with a checkpointer).
graph = builder.compile()