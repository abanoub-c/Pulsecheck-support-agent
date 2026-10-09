"""
Pulsecheck support agent — context manager.

Belongs at: agent/nodes/context_manager.py

Runs first in the graph, before the router, on every turn. Two jobs:
1. Detects a returning customer after a real gap and injects a note
   (with live ticket history from the CRM, not just replayed chat).
2. Keeps the persisted transcript bounded by folding old messages into
   a rolling summary and removing them from state via RemoveMessage.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from langchain_core.messages import RemoveMessage, SystemMessage
from langchain_groq import ChatGroq

from agent.state import SupportState
from agent.tools import get_recent_tickets  # reuse, don't re-implement the HTTP call
from langchain_core.messages import RemoveMessage, SystemMessage, ToolMessage

logger = logging.getLogger(__name__)

SESSION_GAP_HOURS = float(os.getenv("SESSION_GAP_HOURS", "1"))
MAX_RAW_MESSAGES = int(os.getenv("MAX_RAW_MESSAGES", "20"))
KEEP_RECENT_MESSAGES = int(os.getenv("KEEP_RECENT_MESSAGES", "8"))

summarizer_llm = ChatGroq(model="openai/gpt-oss-20b", temperature=0, api_key=os.getenv("GROQ_API_KEY"))


def context_manager_node(state: SupportState) -> dict:
    now = datetime.now(timezone.utc)
    updates: dict = {"last_activity_at": now.isoformat() ,  "turn_count": 0,}
    new_messages = []

    # --- returning-customer detection ---
    last_activity_raw = state.get("last_activity_at")
    if last_activity_raw and state.get("customer_id"):
        gap_hours = (now - datetime.fromisoformat(last_activity_raw)).total_seconds() / 3600
        if gap_hours >= SESSION_GAP_HOURS:
            note = [f"This customer is returning after a {gap_hours:.1f}-hour gap."]
            if state.get("conversation_summary"):
                note.append(f"Summary of the earlier conversation: {state['conversation_summary']}")
            try:
                result = get_recent_tickets.invoke({"customer_id": state["customer_id"], "days": 14})
                tickets = result.get("tickets", []) if isinstance(result, dict) else []
                if tickets:
                    lines = [
                        f"- [{t.get('status', '?')}] {t.get('category', '?')}: {t.get('subject', '(no subject)')}"
                        for t in tickets
                    ]
                    note.append("Their recent tickets on file:\n" + "\n".join(lines))
            except Exception as e:
                logger.warning("context_manager: recent ticket lookup failed: %s", e)
            note.append(
                "Greet them naturally. If their new message plausibly continues one "
                "of these, acknowledge it briefly. If it's unrelated, don't force a "
                "callback to the old issue."
            )
            new_messages.append(SystemMessage(content="\n\n".join(note)))

    # --- long-context trim: fold old messages into a summary, drop the raw ones ---
    messages = state.get("messages", [])
    if len(messages) > MAX_RAW_MESSAGES and MAX_RAW_MESSAGES > KEEP_RECENT_MESSAGES:
        cut = len(messages) - KEEP_RECENT_MESSAGES
        while cut < len(messages) and isinstance(messages[cut], ToolMessage):
            cut += 1
        
        to_summarize = messages[:cut]

        if to_summarize:
            transcript = "\n".join(f"{m.type}: {m.content}" for m in to_summarize if hasattr(m, "content"))
            prior = state.get("conversation_summary")
            prompt = (
                "Summarize this support conversation in 4-6 sentences, keeping specific "
                "facts (amounts, dates, ticket IDs, resolved vs still open).\n"
                + (f"Existing summary to fold in: {prior}\n\n" if prior else "")
                + f"Conversation:\n{transcript}"
            )
            updates["conversation_summary"] = summarizer_llm.invoke(prompt).content
            removals = [RemoveMessage(id=m.id) for m in to_summarize if getattr(m, "id", None)]
            updates["messages"] = removals + new_messages
        elif new_messages:
            updates["messages"] = new_messages
    elif new_messages:
        updates["messages"] = new_messages

    return updates