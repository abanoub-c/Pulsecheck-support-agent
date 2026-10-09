"""
Pulsecheck support agent — CRM Tool Wrappers.

Belongs at: agent/tools.py

These are the thin wrappers around the FastAPI backend. 
LangChain's @tool decorator automatically extracts the docstrings and 
type hints to tell the LLM exactly how and when to use these functions.
"""

import requests
from typing import Optional, Literal
from langchain_core.tools import tool
import httpx


# The base URL where your FastAPI mock CRM is running
API_BASE = "http://127.0.0.1:8000"

# ===========================================================================
# BILLING AGENT TOOLS
# ===========================================================================

@tool
def get_subscription(customer_id: str) -> dict:
    """Fetch the customer's current subscription details, plan limits, and billing status.
    Always use this to check plan tiers or monitor limits before answering billing questions."""
    try:
        response = requests.get(f"{API_BASE}/subscriptions/{customer_id}")
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        return {"error": f"Failed to fetch subscription: {e.response.text}"}

@tool
def get_invoices(customer_id: str) -> dict:
    """Fetch the customer's invoice history. Use this to check for failed payments or past charges.
    Returns {"count": n, "invoices": [...]}."""
    try:
        response = requests.get(f"{API_BASE}/invoices/{customer_id}")
        response.raise_for_status()
        invoices = response.json()
        return {"count": len(invoices), "invoices": invoices}
    except requests.HTTPError as e:
        return {"error": f"Failed to fetch invoices: {e.response.text}"}

@tool
def change_subscription_plan(customer_id: str, new_tier: str) -> dict:
    """Change a customer's subscription to a different plan tier (upgrade
    or downgrade), applying correct mid-cycle proration automatically.

    Use this whenever a customer wants to move to a different plan tier.
    Do NOT try to calculate proration yourself or use apply_credit for a
    plan change — this tool handles the math server-side:
    - Downgrades: the unused value from the current plan is credited to
      the customer's account balance and applied automatically to their
      next invoice. No charge happens now.
    - Upgrades: the prorated cost difference for the rest of the current
      cycle is charged immediately.

    If a tool returns an error, retry at most once. Then tell the customer plainly that you couldn't complete the request. Never say you have flagged, escalated or notified anyone unless a tool call actually did so.

    Args:
        customer_id: The customer's ID.
        new_tier: The target plan tier — one of "starter", "team", "business".

    Returns:
        old_tier, new_tier, days_remaining, days_in_cycle, prorated_delta,
        immediate_charge (0.00 if a credit was applied instead of a charge),
        and new_account_balance. Returns {"error": ...} if the customer or
        subscription isn't found, the tier is invalid, or they're already
        on that tier.
    """
    try:
        response = requests.post(
            f"{API_BASE}/subscriptions/{customer_id}/change-plan",
            json={"new_tier": new_tier},
        )
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        return {"error": f"Failed to change plan: {e.response.text}"}

@tool
def apply_credit(customer_id: str, amount: float, reason: str) -> dict:
    """Apply a one-off goodwill account credit — e.g. compensation for
    downtime or a service issue unrelated to a plan change.

    Do NOT use this for plan upgrades/downgrades — use
    change_subscription_plan instead, which calculates and applies the
    correct proration on its own. Only use this tool when the credit is
    a standalone goodwill gesture with no plan change involved.

    Args:
        customer_id: The customer's ID.
        amount: The credit amount in dollars (must be positive).
        reason: Brief explanation of why the credit is being issued —
            stored on the account for audit purposes.

    Returns:
        status, amount_credited, reason, and new_account_balance. Returns
        {"error": ...} if the customer or subscription isn't found.
    """
    try:
        response = requests.post(
            f"{API_BASE}/subscriptions/{customer_id}/credit",
            json={"amount": amount, "reason": reason},
        )
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        return {"error": f"Failed to apply credit: {e.response.text}"}

@tool
def update_payment_method_link(customer_id: str) -> str:
    """Generate a secure, one-time link for the customer to update their credit card on file."""
    # STUB: Simulates a Stripe Customer Portal session link.
    return f"https://billing.pulsecheck.com/update-card/session_{customer_id.lower()}_8a9b2c"


# ===========================================================================
# TECHNICAL AGENT TOOLS
# ===========================================================================


INCIDENT_STATUSES = ("open", "monitoring", "resolved")

@tool
def check_known_incidents() -> dict:
    """Check the known-incident list for platform-wide outages and bugs, both ongoing
    and recently resolved.

    ALWAYS call this before treating a customer's alert, outage or monitor problem as a
    new issue. It takes no arguments and returns EVERY incident, because a customer
    reporting something that happened "yesterday" is usually describing an incident
    that is already resolved.

    Returns {"count": n, "incidents": [...]}. When an incident matches the customer's
    problem, cite its incident_id and use its customer_facing_note in your reply
    instead of creating a ticket.
    """
    incidents: list[dict] = []
    seen: set[str] = set()
    try:
        for s in INCIDENT_STATUSES:
            r = requests.get(f"{API_BASE}/incidents", params={"status": s}, timeout=10)
            r.raise_for_status()
            for inc in r.json():
                if inc["incident_id"] not in seen:
                    seen.add(inc["incident_id"])
                    incidents.append(inc)
        return {"count": len(incidents), "incidents": incidents}
    except requests.RequestException as e:
        return {"error": f"Failed to check incidents: {e}"}

@tool
def get_recent_tickets(customer_id: str, days: int = 14) -> list[dict]:
    """Check this customer's recent ticket history to avoid creating a
    duplicate ticket for an issue they already reported.

    Call this BEFORE create_bug_ticket, in addition to check_known_incidents.
    check_known_incidents catches platform-wide outages; this catches the
    case where this specific customer already filed a ticket for their own
    issue, even if it's not a known platform incident.

    Args:
        customer_id: The customer's ID.
        hours: How many hours back to search (default 72).

    Returns:
        A list of recent tickets for this customer, most recent first, each
        with ticket_id, category, subject, message, status, created_at,
        and resolution_notes (if resolved). Empty list if none found.
    """
    try:
        resp = httpx.get(
            f"{API_BASE}/tickets",
            params={"customer_id": customer_id, "category": "technical", "days": days},
            timeout=10.0,
        )
        resp.raise_for_status()
        tickets = resp.json()
        return {"count": len(tickets), "tickets": tickets}
    except httpx.HTTPError as e:
        return {"error": f"Failed to fetch recent tickets: {e}"}
@tool
def create_bug_ticket(customer_id: str, subject: str, message: str, subtype: str) -> dict:
    """Create a technical support ticket for the human engineering team when an issue is unknown.
    Requires customer_id, a short subject, a detailed message, and a subtype (e.g., 'webhook_failure', 'api_latency')."""
    try:
        payload = {
            "customer_id": customer_id,
            "category": "technical",
            "subtype": subtype,
            "subject": subject,
            "message": message,
            "status": "open"
        }
        response = requests.post(f"{API_BASE}/tickets", json=payload)
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        return {"error": f"Failed to create ticket: {e.response.text}"}

@tool
def get_monitor_status(endpoint_url: str) -> dict:
    """Check the real-time ping status of a specific customer endpoint URL (e.g., to see if it is currently up or down)."""
    # STUB: Simulates querying an external monitoring system like Datadog or Pingdom.
    return {
        "url": endpoint_url,
        "status": "UP",
        "latency_ms": 145,
        "last_checked": "Just now",
        "message": "Endpoint is healthy and responding to GET requests."
    }

@tool
def resend_webhook_test(customer_id: str, endpoint_id: str) -> dict:
    """Trigger a manual test webhook to the customer's server to verify connectivity."""
    # STUB: Simulates an internal system action.
    return {
        "status": "delivered",
        "http_response_code": 200,
        "message": "Test webhook payload successfully delivered."
    }

# agent/tools.py
@tool
def get_historical_stats(customer_id: str, days: int = 30) -> dict:
    """Get a summary report of this customer's endpoint downtime history.

    Use this when a customer asks how many times their endpoint(s) went
    down/failed, or wants an uptime summary, over a recent period (e.g.
    "how many times did my API fail this month?").

    Args:
        customer_id: The customer's ID.
        days: How many days back to summarize (default 30).

    Returns:
        Aggregate stats (total events, total downtime minutes, breakdown
        by endpoint, how many were part of a known platform incident) plus
        the individual events, most recent first.
    """
    resp = httpx.get(
        f"{API_BASE}/monitors/{customer_id}/stats",
        params={"days": days},
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()

# ===========================================================================
# REFUND AGENT TOOLS
# ===========================================================================

@tool
def issue_refund(customer_id: str, amount: float, reason: str, confirmed: bool) -> dict:
    """Issue a refund to the customer. REQUIRES explicit customer
    confirmation of the exact amount — ask "I'll refund $X, is that
    correct?" and only call this with confirmed=True after they say yes.

    Amounts under $100 are auto-approved once confirmed. Amounts $100 or
    over are still placed in 'pending_review' for a manager — that
    threshold check happens separately and applies regardless of confirmation.
    """
    try:
        payload = {"customer_id": customer_id, "amount": amount, "reason": reason,
                    "currency": "USD", "confirmed": confirmed}
        response = requests.post(f"{API_BASE}/refunds", json=payload)
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        return {"error": f"Refund failed: {e.response.text}"}

@tool
def cancel_subscription(customer_id: str, confirmed: bool) -> dict:
    """Cancel a customer's subscription. REQUIRES explicit customer
    confirmation — you must ask a direct yes/no confirmation question in
    the conversation and only call this with confirmed=True after they
    say yes. Never set confirmed=True preemptively.

    Before calling this, check get_subscription's retention_offer_used:
    - If True (a discount was already used before): just confirm — ask
      "Are you sure you want to cancel your subscription?" and call this
      with confirmed=True only after they say yes.
    - If False: offer apply_retention_discount FIRST. Ask the customer to
      choose between (a) keeping the subscription with the discount, or
      (b) cancelling anyway and losing the offer. If they choose (a), do
      NOT call this tool — call apply_retention_discount and stop there.
      Only call this tool if they choose (b) and then confirm.

    Args:
        customer_id: The customer's ID.
        confirmed: True only if the customer just explicitly confirmed
            cancellation in their latest message.

    Returns:
        status, customer_id, cancelled_at, message. Returns {"error": ...}
        if confirmed is False, the customer isn't found, or already cancelled.
    """
    try:
        response = requests.post(
            f"{API_BASE}/subscriptions/{customer_id}/cancel",
            json={"confirmed": confirmed},
        )
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        return {"error": f"Failed to cancel subscription: {e.response.text}"}
@tool
def apply_retention_discount(customer_id: str, discount_percent: int, duration_months: int, reason: str) -> dict:
    """Offer a temporary retention discount to a customer considering
    cancelling primarily due to cost/pricing — NOT for technical or
    product-dissatisfaction complaints.

    Use this BEFORE cancel_subscription when the customer's stated reason
    is price. Server-side policy limits: discount_percent 5-25,
    duration_months 1-6. Requests at or under 20% for up to 3 months are
    auto-approved; anything higher returns status="pending_review" —
    if you see that, do NOT tell the customer it's active, tell them it's
    been submitted for manager approval and escalate.

    Args:
        customer_id: The customer's ID.
        discount_percent: Discount percentage to offer (5-25).
        duration_months: How many months the discount lasts (1-6).
        reason: Why this discount is being offered — stored for audit.

    Returns:
        status ("applied" or "pending_review"), discount_percent,
        duration_months, discount_expires_at, message. Returns
        {"error": ...} if the customer already used a retention offer
        or input is invalid.
    """
    try:
        response = requests.post(
            f"{API_BASE}/subscriptions/{customer_id}/retention-discount",
            json={
                "discount_percent": discount_percent,
                "duration_months": duration_months,
                "reason": reason,
            },
        )
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        return {"error": f"Failed to apply retention discount: {e.response.text}"}

