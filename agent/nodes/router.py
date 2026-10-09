"""
Pulsecheck support agent — Intent Router / Classifier Node.

Belongs at: agent/nodes/router.py

This node reads the latest customer message, performs a single LLM call with 
forced structured output (category, confidence, reasoning), and updates the 
SupportState without invoking any tools.
"""

from __future__ import annotations

import datetime
from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI  # Or your preferred chat model integration
import os
from langchain_groq import ChatGroq

from agent.state import SupportState, TicketCategory

# ---------------------------------------------------------------------------
# Structured Output Schema for the Classifier
# ---------------------------------------------------------------------------
class ClassificationResult(BaseModel):
    category: list[Literal["billing", "technical", "refund", "other"]] = Field(
        description="One or more categories this ticket touches, ordered "
                    "by relevance. Most tickets have exactly one."
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence score between 0.0 and 1.0 indicating how certain the classifier is."
    )
    reasoning: str = Field(
        description="Brief explanation of why this category and confidence score were chosen."
    )
    wants_human: bool = Field(
    default=False,
    description=(
        "True ONLY if the customer explicitly asks to speak with a human, "
        "agent, manager, or support representative. Frustration or "
        "complaints alone do NOT count."
    ),
    )
    is_smalltalk: bool = Field(
        default=False,
        description="True only for a greeting, thanks, goodbye, or acknowledgement "
                    "with no request or problem in it.",
    )

# ---------------------------------------------------------------------------
# Router Node Functions
# ---------------------------------------------------------------------------
def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b if isinstance(b, str) else str(b.get("text", ""))
            for b in content if isinstance(b, (str, dict))
        )
    return "" if content is None else str(content)


def _recent_context(messages: list, latest_idx: int, max_lines: int = 4) -> str:
    lines = []
    for m in messages[max(0, latest_idx - 8):latest_idx]:
        text = _text(m.content).strip()
        if not text:
            continue
        if isinstance(m, HumanMessage):
            lines.append(f"Customer: {text}")
        elif isinstance(m, AIMessage) and not m.tool_calls:
            lines.append(f"Assistant: {text}")
    return "\n".join(lines[-max_lines:])


def _classifier_input(state: SupportState, latest_idx: int, user_text: str) -> str:
    parts = []
    if state.get("conversation_summary"):
        parts.append(f"Summary of earlier conversation: {state['conversation_summary']}")
    if state.get("category"):
        parts.append(f"Active topic: the customer is mid-conversation with the "
                     f"'{state['category']}' specialist.")
    context = _recent_context(state["messages"], latest_idx)
    if context:
        parts.append(f"Recent messages (context only, do not classify these):\n{context}")
    parts.append(f"LATEST CUSTOMER MESSAGE (classify this one):\n{user_text}")
    return "\n\n".join(parts)

def _classify(structured_llm, messages, attempts=3):
    for i in range(attempts):
        try:
            return structured_llm.invoke(messages)
        except Exception as e:
            if i == attempts - 1 or "tool_use_failed" not in str(e):
                raise

def router_node(state: SupportState) -> dict:
    """Classifies the customer's intent from the latest message.
    
    Evaluates confidence thresholds to determine if the agent can route 
    to a specialist, needs to ask a clarifying question, or must escalate.
    """
    

    # 1. Extract the latest user message from the state transcript
    messages = state["messages"]
    latest_idx = next((i for i in range(len(messages) - 1, -1, -1)
                    if isinstance(messages[i], HumanMessage)), None)

    if latest_idx is None:
        return {
            "confidence": 0.0,
            "classification_reasoning": "No human message found to classify.",
            "resolution_status": "open",
        }

    user_text = _text(messages[latest_idx].content)

    # 2. Initialize the Chat Model and enforce structured output
    # (Ensure your OPENAI_API_KEY environment variable is set)
    llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0,
    api_key=os.getenv("GROQ_API_KEY")
    )
    structured_llm = llm.with_structured_output(ClassificationResult, method="json_schema")

    system_prompt = (
        "You are the front-line triage router for Pulsecheck, a SaaS monitoring platform. "
        "Analyze the customer's latest message and classify it.\n\n"
        "CATEGORIES (a ticket can touch more than one; list them by relevance):\n"
        "- 'billing': Invoices, subscription tiers, plan upgrades or downgrades (including proration), monitor limits, payment failures, and goodwill account credits for downtime or service issues.\n"
        "- 'technical': System outages, webhook delivery issues, broken monitors, slow API latency, bugs.\n"
        "- 'refund': Requests for money back to the customer's card or payment method, and cancelling a subscription or trial.\n"
        "- 'other': Off-topic questions or text that fits none of the above.\n\n"
        "Classify by what the customer is asking us to DO, not by background they mention. "
        "CONVERSATION CONTEXT: you may be shown recent messages and an active topic. "
        "Classify ONLY the latest customer message; use earlier messages just to understand it.\n"
        "- If the latest message replies to the assistant's last message (accepting or declining an "
        "offer, answering a question, yes/no, giving requested details), it belongs to the active topic. "
        "Output that category with confidence 0.85+. Do NOT reclassify because it mentions a word like "
        "'discount', 'credit', 'refund' or 'plan'. Example: after the assistant offered a retention "
        "discount, 'the discount sounds good' is 'refund', not 'billing'.\n"
        "- If the assistant just asked which department this is about, a reply like 'billing' is that "
        "category with high confidence.\n"
        "- Output a different category only when the customer clearly starts a NEW, separate request.\n"
        "CANCELLATION TIE-BREAK: anything about leaving, cancelling, ending or not continuing "
        "(including during a trial) is 'refund', even if the customer also asks whether they will be charged.\n\n"
        "A request for a credit that mentions downtime is 'billing', not 'technical'.\n\n"
        "CONFIDENCE (0.0-1.0): how sure you are which department should handle the message. Use these anchors:\n"
        "- 0.85-1.0: the customer clearly states a request that belongs to one category "
        "(e.g. 'my card was declined', 'cancel my subscription').\n"
        "- 0.60-0.74: a genuine support request about their account or Pulsecheck that does not say what they "
        "need, so the department is unclear (e.g. 'I have a question about my account', 'I need help with "
        "something', 'something is wrong'). Use category ['other'].\n"
        "- 0.00-0.30: gibberish, no meaning, or nothing to do with support.\n"
        "Do NOT score a message below 0.45 just because the category is unclear. A vague but genuine support "
        "request is 0.60-0.74. For reference: 0.75 and above routes to a specialist, 0.45-0.74 triggers one "
        "clarifying question, below 0.45 goes to a human.\n\n"
        "FLAGS:\n"
        "- is_smalltalk: set to true ONLY when the message is purely a greeting, thanks, goodbye, or "
        "acknowledgement (e.g. 'hi', 'thanks!', 'ok great, bye') and contains NO request, problem, "
        "question, name, ID, number, or other information. If the message contains ANY substantive "
        "content, set is_smalltalk=false, even when it starts with 'okay', 'thanks', or 'sure'. "
        "Example: 'okay that's my company name Crestpoint Systems' is NOT smalltalk, because it "
        "provides information. When in doubt, set is_smalltalk=false.\n"
        "- wants_human: set to true ONLY if the customer explicitly asks for a real person, agent, "
        "manager, or representative. Frustration or complaints alone do not count.\n\n"
        "Short replies that answer a question (a name, an ID, 'yes', 'no') are not smalltalk and are "
        "not off-topic. Classify them as low-confidence rather than 'other' with high confidence."
    )
    try:
        # 3. Execute the single classification LLM call
        result = _classify(structured_llm, [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _classifier_input(state, latest_idx, user_text)},
        ])
    except Exception as e:
        print(f"\n🚨 ROUTER EXCEPTION CAUGHT: {str(e)}\n")
        # Fallback if LLM call fails
        return {
            
            "confidence": 0.0,
            "classification_reasoning": f"Classification LLM call failed: {str(e)}",
            "escalation_reason": "tool_call_failed",
            "resolution_status": "escalated"
        }

    # 4. Evaluate Thresholds & Determine Next State Updates
    # Threshold rules:
    # - High confidence (>= 0.75): Route directly to specialist
    # - Medium confidence (0.45 - 0.75): Trigger clarification if first attempt, else escalate
    # - Low confidence (< 0.45): Direct escalation for human review
    
    confidence = result.confidence
    category = result.category
    reasoning = result.reasoning
    clarify_attempts = state.get("clarify_attempts", 0)

    updates = {
        "confidence": confidence,
        "classification_reasoning": reasoning,
    }

    # Log this action into the audit trail
    audit_record = {
        "node": "router",
        "tool": "llm_classification",
        "arguments": {"text": user_text},
        "result": {"category": category, "confidence": confidence},
        "success": True,
        "error": None,
        "timestamp": datetime.datetime.now().isoformat()
    }
    updates["actions_taken"] = [audit_record]
    
    
    active_category = state.get("category")

    ## Handling small talks like thanks
    if result.is_smalltalk and not active_category:
        updates["resolution_status"] = "open"   # explicit: don't inherit a stale "escalated"
        updates["pending_categories"] = []
        updates["clarify_attempts"] = 0
        updates["messages"] = [AIMessage(content=(
            "Happy to help! If there's anything else, whether billing, "
            "a technical issue, or a refund, just let me know."
        ))]
        return updates
    ## human want Escalation
    if result.wants_human:
        updates["resolution_status"] = "escalated"
        updates["escalation_reason"] = "customer_requested_human"
        updates["pending_categories"] = []
        updates["clarify_attempts"] = 0
        # Best guess at the topic, so the ops queue shows which department
        updates["category"] = next((c for c in category if c != "other"), None)
        return updates
    
    if active_category:
        real_topics = [c for c in category if c != "other"]
        top_pick = real_topics[0] if real_topics else None
        is_real_switch = (
            top_pick is not None
            and top_pick != active_category
            and confidence >= 0.75
        )
        if not is_real_switch:
            updates["actions_taken"] = [{
                **audit_record,
                "result": {"action": "stayed_with_active_category", "category": active_category},
            }]
            return updates

    
    if confidence < 0.45:
        updates["resolution_status"] = "escalated"
        updates["escalation_reason"] = "low_confidence"
    elif 0.45 <= confidence < 0.75:
        if clarify_attempts == 0:
            updates["clarify_attempts"] = clarify_attempts + 1
            updates["resolution_status"] = "open"
            updates["pending_categories"] = []
            updates["messages"] = [AIMessage(content=(
                "Just to make sure I route this correctly — is this about your "
                "billing/subscription, a technical issue with your monitors, "
                "or a refund/cancellation request?"
            ))]
        else:
            updates["resolution_status"] = "escalated"
            updates["escalation_reason"] = "clarification_exhausted"
            updates["pending_categories"] = []
    else:
        # High confidence -> populate the queue for dispatch
        filtered = list(dict.fromkeys(c for c in category if c != "other"))
        updates["pending_categories"] = filtered
        updates["clarify_attempts"] = 0
        updates["resolution_status"] = "open" if filtered else "escalated"
        if not filtered:
            updates["escalation_reason"] = "uncategorized_request"  # or add a
            # dedicated "uncategorizable" reason — see note below

    return updates