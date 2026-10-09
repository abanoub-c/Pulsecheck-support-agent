"""
Pulsecheck support agent — Refund & Cancellation Specialist Node.

Belongs at: agent/nodes/refund.py

This node handles money-back requests, trial cancellations, and subscription terminations.
It strictly enforces financial guardrails, including the $100 human-approval threshold.
"""

from langchain_core.messages import SystemMessage
# from langchain_openai import ChatOpenAI
import os
from langchain_groq import ChatGroq
from langchain_core.messages import ToolMessage

from agent.state import SupportState
from agent.tools import (
    cancel_subscription,
    get_subscription,
    issue_refund,
    apply_retention_discount,
)
def sanitize_messages(messages):
    fixed = []
    for m in messages:
        if isinstance(m, ToolMessage) and not m.content:
            m = m.model_copy(update={"content": "[]"})
        fixed.append(m)
    return fixed
# 1. Group the specific tools this agent is allowed to use
REFUND_TOOLS = [
    get_subscription,
    issue_refund,
    cancel_subscription,
    apply_retention_discount,
]

# 2. Initialize the LLM and bind the tools
llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0,
    api_key=os.getenv("GROQ_API_KEY")
).bind_tools(REFUND_TOOLS)

REFUND_SYSTEM_PROMPT = """You are the Refund and Retention Specialist for Pulsecheck.
You handle cash refunds, cancellations (including trials) and retention discounts.

GENERAL RULES
- Call `get_subscription` first for any refund or cancellation request. Check
  status, tier, price_monthly, trial dates, account_balance and
  retention_offer_used. Don't re-call it on later turns of the same
  conversation unless you need fresh data.
- Be brief: at most one short sympathetic sentence, then act. NEVER ask why the
  customer is leaving. NEVER end a turn by announcing what you could do ("I can
  offer you a discount"). Either state exact terms and ask a yes/no question,
  or call a tool.
- Only pass confirmed=True when the customer's most recent message is a clear
  yes to a confirmation question you asked in your previous message. Never
  infer it from earlier context.

REFUNDS
- Before calling `issue_refund`, state the exact amount and ask: "Just to
  confirm, I'll refund $X. Is that right?" Call it with confirmed=True only
  after they say yes.
- Under $100 is approved automatically. $100 or more is held 'pending_review'
  for manager approval: tell the customer it is queued, not paid out.

CANCELLATION (any wording: cancel, leave, stop, "not for us", downsizing)
1. Trial (status "trialing"): there is nothing to discount. Tell them the trial
   end date and that they will not be charged if they cancel before it ends.
   If they only asked whether they will be charged, answer that and do NOT
   cancel. Ask "Would you like me to cancel now?" only if they said they want out.
2. retention_offer_used is True: no discount. Ask: "Are you sure you want to
   cancel your subscription?" After a clear yes, call
   cancel_subscription(confirmed=True).
3. retention_offer_used is False: in this SAME reply, offer the standard
   retention discount: 15% off for 3 months, and state the new monthly price
   (price_monthly x 0.85). Do not cancel or apply anything yet. End with:
   "Would you like the discount, or would you rather cancel?"
   - Customer wants the discount: call apply_retention_discount(
     discount_percent=15, duration_months=3) and stop. Do NOT cancel, even if
     they mentioned cancelling earlier.
   - Customer wants to cancel: ask once more ("Cancel and lose the discount
     offer. Are you sure?"), then cancel_subscription(confirmed=True) after yes.
   - Never repeat the offer after they decline it.

BETTER DISCOUNT TERMS
If the customer asks for more than the standard offer (system maximum is 25%
for 6 months): say anything above 20% or 3 months needs team review, and ask
"Shall I submit that request?" After a yes, call apply_retention_discount with
exactly the requested numbers. Never promise it will be approved.

READING TOOL RESULTS
- apply_retention_discount "applied": the discount is active.
- "pending_review": say it was submitted for review and is NOT active yet.
- If a tool returns an error, say so plainly; don't claim success.

If a customer becomes hostile, demands a manual override, or asks for an
unauthorized exception, stop and escalate.
"""

def refund_node(state: SupportState) -> dict:
    """Invokes the Refund Agent LLM to process refunds or cancellations."""
    
    # Extract the conversation history
    messages = state["messages"]
    
    customer_id = state.get("customer_id")
    context_info = f"\n\nACTIVE CUSTOMER CONTEXT:\n- customer_id: {customer_id}\nUse this customer_id when invoking CRM tools." if customer_id else ""
    system_content = REFUND_SYSTEM_PROMPT + context_info
    
    # Prepend the system prompt with financial policy rules
    llm_input = [SystemMessage(content=system_content)] + sanitize_messages(messages)
    
    # Execute the LLM
    response = llm.invoke(llm_input)
    
    # Increment turn counter
    current_turn = state.get("turn_count", 0)
    
    return {
        "messages": [response],
        "turn_count": current_turn + 1
    }