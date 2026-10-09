"""
Pulsecheck support agent — shared graph state.


This is the single object every LangGraph node reads from and writes back
to. It's deliberately shaped around the CRM contract actually built in
backend/app/models.py and backend/app/main.py, not just the plan's original
sketch:

  - `ticket_id`, `refund_id`, `escalation_id` are the real string IDs the
    CRM generates (e.g. "TICK-...", "REF-...", "ESC-..."). Once a node
    creates one of these rows, it stashes the ID here so later nodes (and a
    resumed graph, after interrupt()) can look it up again instead of
    re-deriving it from the audit trail.
  - `proposed_action` is a first-class field rather than "the last entry in
    actions_taken" — the refund agent drafts a proposed refund/cancellation
    here, escalate_to_human() packages it into the interrupt() payload, and
    whatever the human decides gets applied from this field, not guessed at.
  - Confidence is kept as a plain `float` here even though the CRM's
    `EscalationCreate.confidence` is a `Decimal` — convert at the tool
    boundary (`Decimal(str(confidence))`) rather than carrying Decimal
    through the graph.

Reducers:
  - `messages` uses LangGraph's `add_messages` so each node can return just
    the new message(s) it produced and have them appended, not replace the
    whole transcript.
  - `actions_taken` uses `operator.add` for the same reason — it's an
    append-only audit trail, so every node returns only its own new
    record(s).
  - Every other field is plain last-write-wins, which is what you want for
    things like `category` or `resolution_status`: a node explicitly
    computes the new value and returns it.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

# ---------------------------------------------------------------------------
# Literal aliases — keep these in sync with the values your CRM actually
# stores (backend/app/models.py) and the routing table in build plan §6.
# ---------------------------------------------------------------------------

TicketCategory = Literal["billing", "technical", "refund", "other"]

ResolutionStatus = Literal["open", "resolved", "escalated"]

EscalationReason = Literal[
    "low_confidence",  # classifier confidence < 0.45
    "clarification_exhausted",  # 0.45-0.75, and the one re-classify attempt didn't clear the bar
    "refund_exceeds_threshold",  # amount >= $100, so the CRM created it as pending_review
    "tool_call_failed",  # e.g. customer not found, downstream API error
    "customer_requested_human",
    "loop_guard_exceeded",  # more than 4 back-and-forth turns without resolution
    "uncategorized_request",
]


class ActionRecord(TypedDict):
    """One entry in the audit trail — every tool call and its outcome.

    This is the artifact §3 of the build plan calls out as what a human
    reviewer (or a client in a demo) checks first: not just what the agent
    said, but which CRM calls it actually made and whether they succeeded.
    """

    node: str  # which graph node made the call, e.g. "refund_agent"
    tool: str  # tool/function name, e.g. "issue_refund"
    arguments: dict[str, Any]
    result: Optional[dict[str, Any]]  # None if the call failed
    success: bool
    error: Optional[str]  # populated when success is False
    timestamp: str  # ISO 8601, set by the node when the call completes


class SupportState(TypedDict):
    # --- conversation identity ---------------------------------------------
    thread_id: str
    # Optional rather than required: a lookup can fail mid-conversation
    # (wrong/stale ID), which is itself a "tool_call_failed" escalation
    # trigger — the field needs to be able to represent that unresolved state.
    customer_id: Optional[str]
    #---- Context manegment------------
    last_activity_at: Optional[str]       # ISO 8601, updated every graph run
    conversation_summary: Optional[str]   # rolling summary of trimmed-away messages

    # --- transcript -----------------------------------------------------
    messages: Annotated[list[BaseMessage], add_messages]

    # --- classification ---------------------------------------------------
    category: Optional[TicketCategory]
    
    pending_categories: list[TicketCategory]

    confidence: Optional[float]
    classification_reasoning: Optional[str]
    clarify_attempts: int  # 0 until the router asks its one clarifying question

    # --- loop guard -------------------------------------------------------
    turn_count: int  # back-and-forth turns in the current specialist hand-off

    # --- CRM record links ---------------------------------------------------
    ticket_id: Optional[str]
    refund_id: Optional[str]
    escalation_id: Optional[str]

    # --- resolution & escalation --------------------------------------------
    resolution_status: ResolutionStatus
    escalation_reason: Optional[EscalationReason]
    proposed_action: Optional[dict[str, Any]]

    # --- audit trail ------------------------------------------------------
    actions_taken: Annotated[list[ActionRecord], operator.add]


def new_support_state(
    thread_id: str,
    customer_id: Optional[str] = None,
    first_message: Optional[BaseMessage] = None,
) -> SupportState:
    """Build a fresh SupportState for a new conversation.

    Centralizing the defaults here means the CLI harness, the chat
    frontend, and any tests all start a conversation the same way instead
    of each re-typing this dict by hand.
    """
    return SupportState(
        thread_id=thread_id,
        customer_id=customer_id,
        last_activity_at=None,
        conversation_summary=None,
        messages=[first_message] if first_message is not None else [],
        category=None,
        pending_categories=[],
        confidence=None,
        classification_reasoning=None,
        clarify_attempts=0,
        turn_count=0,
        ticket_id=None,
        refund_id=None,
        escalation_id=None,
        resolution_status="open",
        escalation_reason=None,
        proposed_action=None,
        actions_taken=[],
    )