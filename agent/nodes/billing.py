"""
Pulsecheck support agent — Billing Specialist Node.

Belongs at: agent/nodes/billing.py

This node handles all inquiries related to subscriptions, invoices, 
proration, and payment methods. It has exclusive access to the billing tools.
"""

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
import os
from langchain_groq import ChatGroq
from langchain_core.messages import ToolMessage


from agent.state import SupportState
from agent.tools import (
    apply_credit,
    get_invoices,
    get_subscription,
    update_payment_method_link,
    change_subscription_plan,
)

# 1. Group the specific tools this agent is allowed to use
BILLING_TOOLS = [
    get_subscription,
    get_invoices,
    apply_credit,
    update_payment_method_link,
    change_subscription_plan,
]
def sanitize_messages(messages):
    fixed = []
    for m in messages:
        if isinstance(m, ToolMessage) and not m.content:
            m = m.model_copy(update={"content": "[]"})
        fixed.append(m)
    return fixed
# 2. Initialize the LLM and bind the tools
# (Using a low temperature ensures factual, deterministic tool usage)
llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0,
    api_key=os.getenv("GROQ_API_KEY")
).bind_tools(BILLING_TOOLS)

BILLING_SYSTEM_PROMPT = """You are the Billing Support Specialist for Pulsecheck.
Your job is to resolve customer questions about subscriptions, invoices, limits, and payments.

CRITICAL RULES:
1. Always use `get_subscription` to verify a customer's current plan, monitor
   limits, and account_balance before answering questions about their tier
   or billing.
2. If a customer asks about a past charge or failed payment, use `get_invoices`.
3. If a customer needs to update their credit card, generate a link using
   `update_payment_method_link` and provide it to them.
4. If a customer wants to upgrade or downgrade their plan, use
   `change_subscription_plan`. Do not calculate proration yourself and do
   not use `apply_credit` for this, even if the customer phrases it as
   "can you just credit me the difference" — the tool handles proration
   automatically:
   - Downgrades produce a credit toward their account_balance, applied
     automatically to their next invoice (no charge now).
   - Upgrades charge the prorated difference immediately.
   After calling it, tell the customer their new plan, their new
   account_balance, and — for a downgrade — that the credit will reduce
   or zero out their next invoice automatically.
5. Use `apply_credit` ONLY for a standalone goodwill credit unrelated to a
   plan change — e.g. compensation for downtime. Never use it for a plan
   change, and never issue cash refunds (that's handled by the Refund
   department, not you).
6. Be concise, professional, and empathetic. Do not invent data; always
   rely on your tools.

If you cannot resolve the issue, or if the customer explicitly demands to
speak to a manager, you must stop and escalate.
"""

def billing_node(state: SupportState) -> dict:
    """Invokes the Billing Agent LLM to generate a response or tool call."""
    
    # Extract the conversation history
    messages = state["messages"]
    
    customer_id = state.get("customer_id")
    context_info = f"\n\nACTIVE CUSTOMER CONTEXT:\n- customer_id: {customer_id}\nUse this customer_id when invoking CRM tools." if customer_id else ""
    system_content = BILLING_SYSTEM_PROMPT + context_info
    
    # Prepend the system prompt to give the LLM its instructions
    llm_input = [SystemMessage(content=system_content)] + sanitize_messages(messages)
    
    # Execute the LLM
    response = llm.invoke(llm_input)
    
    # Increment the turn counter (part of your loop guardrail)
    current_turn = state.get("turn_count", 0)
    
    return {
        # append the AI's response (which could be text or a tool call request)
        "messages": [response],
        "turn_count": current_turn + 1
    }