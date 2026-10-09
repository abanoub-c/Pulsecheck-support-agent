"""
Pulsecheck support agent — Technical Specialist Node.

Belongs at: agent/nodes/technical.py

This node handles platform outages, bug reports, and webhook failures. 
It features a strict deduplication guardrail: it must check for known 
system incidents before creating new engineering tickets.
"""
from langchain_core.messages import ToolMessage

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
import os
from langchain_groq import ChatGroq
from agent.state import SupportState
from agent.tools import (
    check_known_incidents,
    create_bug_ticket,
    get_monitor_status,
    resend_webhook_test,
    get_recent_tickets,
    get_historical_stats,
)

# 1. Group the specific tools this agent is allowed to use
TECHNICAL_TOOLS = [
    check_known_incidents,
    get_monitor_status,
    create_bug_ticket,
    resend_webhook_test,
    get_recent_tickets,
    get_historical_stats,
]


def sanitize_messages(messages):
    fixed = []
    for m in messages:
        if isinstance(m, ToolMessage) and not m.content:
            m = m.model_copy(update={"content": "[]"})
        fixed.append(m)
    return fixed


# 2. Initialize the LLM and bind the tools
llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0,
    api_key=os.getenv("GROQ_API_KEY")
).bind_tools(TECHNICAL_TOOLS)

TECHNICAL_SYSTEM_PROMPT = """You are the Technical Support Engineer for Pulsecheck.
Your job is to diagnose API latency, monitor downtime, webhook delivery failures, and platform bugs.

Workflow for every technical problem. Follow these steps in order, every time:

1. Call check_known_incidents.
2. If a customer_id is known, ALSO call get_recent_tickets (days=14).
   Do this even when step 1 found a matching incident. An incident match
   does NOT replace the per-customer check.
3. Then decide:
   - The customer already has a ticket covering this issue: reference its
     ticket_id and its status. Do not create a new ticket.
   - An OPEN incident matches: cite its incident_id and use its
     customer_facing_note.
   - A matching incident is RESOLVED but the customer says the problem is
     happening now: say the earlier incident was fixed, and treat this as
     possibly separate. Do not tell them it is the same problem.
   - Neither check finds a match: call create_bug_ticket.

Never call create_bug_ticket if either check found a match.
Never answer a technical problem from check_known_incidents alone.

ONLY if neither check finds a match — the issue is genuinely new — use
`create_bug_ticket`.

ADDITIONAL RULES:
3. If a customer asks if their specific endpoint is down, use `get_monitor_status`.
4. If a customer reports missed Slack/webhook notifications, use `resend_webhook_test`.
5. If a customer asks about their downtime/failure HISTORY (e.g. "how many
   times did my endpoint fail this month", "what's my uptime been like"),
   use `get_historical_stats`. Summarize it as a short report: total
   incidents, total downtime, and call out if any were part of a known
   platform incident (not the customer's fault) vs. isolated failures.
   Don't just dump the raw numbers — write 2-4 sentences a non-technical
   founder could read at a glance.

   
Be precise, technical, and analytical. Do not invent downtime or guess what
an error code means. Rely strictly on your tools.
"""

def technical_node(state: SupportState) -> dict:
    """Invokes the Technical Agent LLM to diagnose bugs or route to known incidents."""
    
    # Extract the conversation history
    messages = state["messages"]
    
    customer_id = state.get("customer_id")
    context_info = f"\n\nACTIVE CUSTOMER CONTEXT:\n- customer_id: {customer_id}\nUse this customer_id when invoking CRM tools." if customer_id else ""
    system_content = TECHNICAL_SYSTEM_PROMPT + context_info
    
    # Prepend the system prompt with the deduplication rules
    llm_input = [SystemMessage(content=system_content)] + sanitize_messages(messages)
    
    # Execute the LLM
    response = llm.invoke(llm_input)
    
    # Increment the turn counter
    current_turn = state.get("turn_count", 0)
    
    return {
        "messages": [response],
        "turn_count": current_turn + 1
    }