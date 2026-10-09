"""
Pulsecheck support agent — dispatcher.

Pops the next category off `pending_categories` and makes it the active
`category`. Sits between the router and the specialists, and between one
specialist and the next, so a hybrid ticket (e.g. billing + technical)
gets routed to each relevant specialist in turn without re-running the
classifier.
"""

from datetime import datetime, timezone
from agent.state import SupportState


def dispatch_node(state: SupportState) -> dict:
    pending = list(state.get("pending_categories", []))

    if not pending:
        return {"category": None}

    next_category = pending.pop(0)

    return {
        "category": next_category,
        "pending_categories": pending,
        "turn_count": 0,
        "actions_taken": [{
            "node": "dispatch",
            "tool": "dispatch_next_category",
            "arguments": {"category": next_category},
            "result": {"remaining": pending},
            "success": True,
            "error": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
    }