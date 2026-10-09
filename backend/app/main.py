"""
Pulsecheck Mock CRM API.

Belongs at: backend/app/main.py

Run locally from this directory with:
    uvicorn main:app --reload

The service uses SQLite + SQLAlchemy and seeds the database once on startup
from seed_data.py. Set PULSECHECK_DATABASE_URL to use another SQLite URL, for
example: sqlite:///./pulsecheck.db

Dev/eval helper: POST /admin/reseed drops every table and reloads the seed
data (disable it with PULSECHECK_ENABLE_ADMIN=0).
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal, Optional
from uuid import uuid4

from dateutil.relativedelta import relativedelta
from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

try:  # Supports both `uvicorn app.main:app` and `uvicorn main:app`.
    from .models import (
        Base,
        Customer,
        DowntimeEvent,
        Escalation,
        Invoice,
        KnownIncident,
        Refund,
        Subscription,
        Ticket,
    )
    from routes.seed_data import (
        CUSTOMERS,
        DOWNTIME_EVENTS,
        INVOICES,
        KNOWN_INCIDENTS,
        REFUNDS,
        SUBSCRIPTIONS,
        TICKETS,
    )
except ImportError:  # pragma: no cover - used when running from backend/app.
    from models import (
        Base,
        Customer,
        DowntimeEvent,
        Escalation,
        Invoice,
        KnownIncident,
        Refund,
        Subscription,
        Ticket,
    )
    from routes.seed_data import (
        CUSTOMERS,
        DOWNTIME_EVENTS,
        INVOICES,
        KNOWN_INCIDENTS,
        REFUNDS,
        SUBSCRIPTIONS,
        TICKETS,
    )

# ---------------------------------------------------------------------------
# Plan-change proration
# ---------------------------------------------------------------------------
PLAN_PRICES = {"starter": Decimal("29.00"), "team": Decimal("99.00"), "business": Decimal("299.00")}
PLAN_LIMITS = {"starter": 5, "team": 25, "business": 100}

# Retention discounts at or under both limits are applied immediately;
# anything above goes to manager review.
AUTO_APPROVE_MAX_DISCOUNT_PERCENT = 20
AUTO_APPROVE_MAX_DURATION_MONTHS = 3


def compute_plan_change(subscription: Subscription, new_tier: str, today: date) -> dict:
    billing_date = subscription.next_billing_date
    if billing_date is None:
        raise HTTPException(
            status_code=400,
            detail="Cannot change plan: subscription has no active billing cycle.",
        )
    if isinstance(billing_date, str):
        billing_date = date.fromisoformat(billing_date)
    elif isinstance(billing_date, datetime):
        billing_date = billing_date.date()

    # NOTE: this guard must stay AFTER days_remaining is assigned.
    days_remaining = (billing_date - today).days
    if days_remaining < 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot prorate: the current billing period has already ended (account may be past due).",
        )

    cycle_start = billing_date - relativedelta(months=1)
    days_in_cycle = (billing_date - cycle_start).days

    old_price = Decimal(str(subscription.price_monthly))
    new_price = Decimal(str(PLAN_PRICES[new_tier]))

    unused_value_old = old_price * Decimal(days_remaining) / Decimal(days_in_cycle)
    cost_new_remaining = new_price * Decimal(days_remaining) / Decimal(days_in_cycle)
    delta = (unused_value_old - cost_new_remaining).quantize(Decimal("0.01"))

    return {
        "old_tier": subscription.tier,
        "new_tier": new_tier,
        "days_remaining": days_remaining,
        "days_in_cycle": days_in_cycle,
        "prorated_delta": delta,
    }


# ---------------------------------------------------------------------------
# App + database setup
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("PULSECHECK_DATABASE_URL", "sqlite:///./pulsecheck.db")
engine_kwargs: dict[str, Any] = {"future": True}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

app = FastAPI(
    title="Pulsecheck Mock CRM",
    description="A small CRM backend used by the Pulsecheck multi-agent support system.",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Pydantic API schemas
# ---------------------------------------------------------------------------


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CustomerRead(ORMModel):
    customer_id: str
    company_name: str
    contact_name: str
    contact_email: str
    signup_date: date
    tier: str
    account_status: str


class SubscriptionRead(ORMModel):
    subscription_id: str
    customer_id: str
    tier: str
    monitor_limit: int
    monitors_used: int
    price_monthly: Decimal
    account_balance: Decimal
    discount_percent: Decimal
    discount_expires_at: date | None
    retention_offer_used: bool
    status: str
    created_at: date
    next_billing_date: date | None
    trial_end_date: date | None
    cancelled_at: date | None
    failed_payment_count: int
    payment_method_last4: str | None


class CancelSubscriptionRequest(BaseModel):
    confirmed: bool = Field(
        description="Must be true. Only set true after the customer has "
        "explicitly confirmed cancellation with a yes/no answer."
    )


class CancelSubscriptionResponse(BaseModel):
    status: str
    customer_id: str
    cancelled_at: date
    message: str


class InvoiceRead(ORMModel):
    invoice_id: str
    customer_id: str
    subscription_id: str | None
    amount: Decimal
    currency: str
    status: str
    invoice_date: date
    due_date: date | None
    paid_at: date | None
    failure_reason: str | None


class KnownIncidentRead(ORMModel):
    incident_id: str
    title: str
    description: str
    affected_component: str
    status: str
    started_at: date
    resolved_at: date | None
    root_cause: str
    customer_facing_note: str


class RefundCreate(BaseModel):
    customer_id: str
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    reason: str = Field(min_length=1, max_length=2000)
    ticket_id: str | None = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    confirmed: bool = Field(
        description="Must be true. Only set after the customer explicitly confirmed the exact refund amount."
    )


class RefundRead(ORMModel):
    refund_id: str
    customer_id: str
    ticket_id: str | None
    amount: Decimal
    currency: str
    reason: str
    status: str
    created_at: date
    processed_at: date | None
    notes: str | None
    auto_approved: bool = False
    approval_message: str = ""


class RefundUpdate(BaseModel):
    status: Literal["approved", "rejected"]
    notes: str | None = None


class TicketRead(ORMModel):
    ticket_id: str
    customer_id: str
    category: str
    subtype: str
    subject: str
    message: str
    status: str
    created_at: date
    resolved_at: date | None
    resolution_notes: str | None


class TicketCreate(BaseModel):
    customer_id: str
    category: str = Field(min_length=1, max_length=20)
    subtype: str = Field(min_length=1, max_length=40)
    subject: str = Field(min_length=1, max_length=240)
    message: str = Field(min_length=1)
    status: str = Field(default="open", min_length=1, max_length=20)
    created_at: date | None = None
    resolved_at: date | None = None
    resolution_notes: str | None = None


class TicketSummary(ORMModel):
    ticket_id: str
    category: str
    subtype: Optional[str]
    subject: str
    message: str
    status: str
    created_at: datetime
    resolved_at: Optional[datetime]
    resolution_notes: Optional[str]


class TicketUpdate(BaseModel):
    category: str | None = Field(default=None, min_length=1, max_length=20)
    subtype: str | None = Field(default=None, min_length=1, max_length=40)
    subject: str | None = Field(default=None, min_length=1, max_length=240)
    message: str | None = Field(default=None, min_length=1)
    status: str | None = Field(default=None, min_length=1, max_length=20)
    resolved_at: date | None = None
    resolution_notes: str | None = None


class EscalationCreate(BaseModel):
    customer_id: str
    category: str = Field(min_length=1, max_length=20)
    ticket_id: str | None = None
    confidence: Decimal | None = Field(default=None, ge=0, le=1, max_digits=4, decimal_places=3)
    reasoning: str | None = None
    proposed_action: dict[str, Any] | None = None
    conversation_summary: str | None = None


class EscalationRead(ORMModel):
    escalation_id: str
    customer_id: str
    ticket_id: str | None
    category: str
    confidence: Decimal | None
    reasoning: str | None
    proposed_action: dict[str, Any] | None
    conversation_summary: str | None
    status: str
    decision: str | None
    decision_note: str | None
    created_at: date
    resolved_at: date | None


class DowntimeEventSummary(ORMModel):
    event_id: str
    endpoint_name: str
    started_at: datetime
    resolved_at: Optional[datetime]
    duration_minutes: Optional[int]
    cause: Optional[str]
    related_incident_id: Optional[str]


class HistoricalStatsResponse(BaseModel):
    customer_id: str
    period_days: int
    total_events: int
    total_downtime_minutes: int
    events_linked_to_known_incident: int
    by_endpoint: dict[str, int]  # endpoint_name -> event count
    events: list[DowntimeEventSummary]  # most recent first


class ChangePlanRequest(BaseModel):
    new_tier: str = Field(min_length=1, max_length=20)


class ChangePlanResponse(BaseModel):
    old_tier: str
    new_tier: str
    days_remaining: int
    days_in_cycle: int
    prorated_delta: Decimal
    immediate_charge: Decimal
    new_account_balance: Decimal


class CreditRequest(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    reason: str = Field(min_length=1, max_length=500)


class CreditResponse(BaseModel):
    status: str
    amount_credited: Decimal
    reason: str
    new_account_balance: Decimal


class RetentionDiscountRequest(BaseModel):
    discount_percent: int = Field(ge=5, le=25)
    duration_months: int = Field(ge=1, le=6)
    reason: str = Field(min_length=1, max_length=500)


class RetentionDiscountResponse(BaseModel):
    status: str  # "applied" | "pending_review"
    customer_id: str
    discount_percent: int
    duration_months: int
    discount_expires_at: date
    reason: str
    message: str


# ---------------------------------------------------------------------------
# Database helpers and startup seed
# ---------------------------------------------------------------------------


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12].upper()}"


def _get_subscription_or_404(db: Session, customer_id: str) -> Subscription:
    subscription = db.scalar(
        select(Subscription).where(Subscription.customer_id == customer_id)
    )
    if subscription is None:
        raise HTTPException(status_code=404, detail=f"Subscription for {customer_id} not found")
    return subscription


def _seed_is_current(db: Session) -> bool:
    """True when the DB is seeded AND has the newest columns and tables.

    create_all() adds missing tables but never missing columns, so an old
    pulsecheck.db fails the column probe and gets rebuilt from seed_data.py.
    """
    try:
        db.execute(
            select(Subscription.account_balance, Subscription.retention_offer_used).limit(1)
        ).first()
        has_customers = db.scalar(select(Customer.customer_id).limit(1)) is not None
        has_downtime = db.scalar(select(DowntimeEvent.event_id).limit(1)) is not None
        return has_customers and has_downtime
    except Exception:
        db.rollback()
        return False


def seed_database(force: bool = False) -> None:
    """Create tables and load seed_data.py for an empty/outdated database or when forced."""
    if force:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if not force:
            if _seed_is_current(db):
                return
            # Outdated schema or half-seeded database: rebuild cleanly.
            db.rollback()
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)

        db.add_all(Customer(**row) for row in CUSTOMERS)
        db.add_all(Subscription(**row) for row in SUBSCRIPTIONS)
        db.add_all(Ticket(**row) for row in TICKETS)
        db.add_all(KnownIncident(**row) for row in KNOWN_INCIDENTS)
        db.add_all(Invoice(**row) for row in INVOICES)
        db.add_all(Refund(**row) for row in REFUNDS)
        db.add_all(DowntimeEvent(**row) for row in DOWNTIME_EVENTS)
        db.commit()


@app.on_event("startup")
def on_startup() -> None:
    seed_database()


# ---------------------------------------------------------------------------
# Health, admin and lookup endpoints
# ---------------------------------------------------------------------------


@app.get("/", tags=["health"])
def root() -> dict[str, str]:
    return {"service": "Pulsecheck Mock CRM", "status": "ok"}


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/admin/reseed", tags=["admin"])
def admin_reseed() -> dict[str, str]:
    """Dev/eval only: drop every table and reload the seed data."""
    if os.getenv("PULSECHECK_ENABLE_ADMIN", "1") != "1":
        raise HTTPException(status_code=404, detail="Not found")
    seed_database(force=True)
    return {"status": "reseeded"}


@app.get("/customers/{customer_id}", response_model=CustomerRead, tags=["customers"])
def get_customer(customer_id: str, db: Session = Depends(get_db)) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
    return customer


@app.get("/subscriptions/{customer_id}", response_model=SubscriptionRead, tags=["subscriptions"])
def get_subscription(customer_id: str, db: Session = Depends(get_db)) -> Subscription:
    return _get_subscription_or_404(db, customer_id)


@app.get("/invoices/{customer_id}", response_model=list[InvoiceRead], tags=["invoices"])
def get_invoices(customer_id: str, db: Session = Depends(get_db)) -> list[Invoice]:
    if db.get(Customer, customer_id) is None:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
    return list(
        db.scalars(
            select(Invoice)
            .where(Invoice.customer_id == customer_id)
            .order_by(Invoice.invoice_date.desc())
        )
    )


@app.get("/incidents", response_model=list[KnownIncidentRead], tags=["incidents"])
def get_incidents(
    status_filter: str | None = Query(default="open", alias="status"),
    db: Session = Depends(get_db),
) -> list[KnownIncident]:
    """status=open (default) returns open + monitoring; status=all returns everything."""
    statement = select(KnownIncident).order_by(KnownIncident.started_at.desc())
    if status_filter in (None, "all"):
        pass
    elif status_filter == "open":
        statement = statement.where(KnownIncident.status.in_(["open", "monitoring"]))
    else:
        statement = statement.where(KnownIncident.status == status_filter)
    return list(db.scalars(statement))


@app.get(
    "/monitors/{customer_id}/stats",
    response_model=HistoricalStatsResponse,
    tags=["monitors"],
)
def get_historical_stats(
    customer_id: str,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> HistoricalStatsResponse:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    events = list(
        db.scalars(
            select(DowntimeEvent)
            .where(DowntimeEvent.customer_id == customer_id)
            .where(DowntimeEvent.started_at >= cutoff)
            .order_by(DowntimeEvent.started_at.desc())
        )
    )

    by_endpoint: dict[str, int] = {}
    for e in events:
        by_endpoint[e.endpoint_name] = by_endpoint.get(e.endpoint_name, 0) + 1

    return HistoricalStatsResponse(
        customer_id=customer_id,
        period_days=days,
        total_events=len(events),
        total_downtime_minutes=sum(e.duration_minutes or 0 for e in events),
        events_linked_to_known_incident=sum(1 for e in events if e.related_incident_id),
        by_endpoint=by_endpoint,
        events=[DowntimeEventSummary.model_validate(e) for e in events],
    )


# ---------------------------------------------------------------------------
# Refunds: the explicit business guardrail
# ---------------------------------------------------------------------------


@app.post("/refunds", response_model=RefundRead, status_code=status.HTTP_201_CREATED, tags=["refunds"])
def issue_refund(payload: RefundCreate, db: Session = Depends(get_db)) -> RefundRead:
    if db.get(Customer, payload.customer_id) is None:
        raise HTTPException(status_code=404, detail=f"Customer {payload.customer_id} not found")
    if payload.ticket_id is not None and db.get(Ticket, payload.ticket_id) is None:
        raise HTTPException(status_code=404, detail=f"Ticket {payload.ticket_id} not found")
    if not payload.confirmed:
        raise HTTPException(status_code=400, detail="Refund requires explicit customer confirmation.")

    # Strictly under $100 is auto-approved. Exactly $100 or more requires review.
    auto_approved = payload.amount < Decimal("100.00")
    refund = Refund(
        refund_id=_new_id("REF"),
        customer_id=payload.customer_id,
        ticket_id=payload.ticket_id,
        amount=payload.amount,
        currency=payload.currency.upper(),
        reason=payload.reason,
        status="approved" if auto_approved else "pending_review",
        created_at=date.today(),
        processed_at=date.today() if auto_approved else None,
        notes=(
            "Automatically approved under the $100 policy threshold."
            if auto_approved
            else "Held for human approval because the amount is $100 or greater."
        ),
    )
    db.add(refund)
    db.commit()
    db.refresh(refund)
    refund_data = RefundRead.model_validate(refund).model_dump(
        exclude={"auto_approved", "approval_message"}
    )
    return RefundRead(
        **refund_data,
        auto_approved=auto_approved,
        approval_message=(
            "Refund approved automatically."
            if auto_approved
            else "Refund created and queued for human approval."
        ),
    )


@app.patch("/refunds/{refund_id}", response_model=RefundRead, tags=["refunds"])
def update_refund(refund_id: str, payload: RefundUpdate, db: Session = Depends(get_db)):
    refund = db.get(Refund, refund_id)
    if not refund:
        raise HTTPException(status_code=404, detail="Refund not found")

    refund.status = payload.status
    if payload.notes:
        refund.notes = payload.notes
    refund.processed_at = date.today()

    db.commit()
    db.refresh(refund)
    return refund


# ---------------------------------------------------------------------------
# Subscriptions: retention discount, cancellation, plan changes, credits
# ---------------------------------------------------------------------------


@app.post(
    "/subscriptions/{customer_id}/retention-discount",
    response_model=RetentionDiscountResponse,
    tags=["subscriptions"],
)
def apply_retention_discount(
    customer_id: str, payload: RetentionDiscountRequest, db: Session = Depends(get_db)
) -> RetentionDiscountResponse:
    sub = _get_subscription_or_404(db, customer_id)

    if sub.retention_offer_used:
        raise HTTPException(
            status_code=409,
            detail="A retention discount has already been used on this account.",
        )

    auto_approved = (
        payload.discount_percent <= AUTO_APPROVE_MAX_DISCOUNT_PERCENT
        and payload.duration_months <= AUTO_APPROVE_MAX_DURATION_MONTHS
    )
    expires_at = date.today() + relativedelta(months=payload.duration_months)

    if not auto_approved:
        return RetentionDiscountResponse(
            status="pending_review",
            customer_id=customer_id,
            discount_percent=payload.discount_percent,
            duration_months=payload.duration_months,
            discount_expires_at=expires_at,
            reason=payload.reason,
            message=(
                f"A {payload.discount_percent}% discount for {payload.duration_months} months "
                "exceeds the self-service limit and requires manager approval."
            ),
        )

    sub.discount_percent = Decimal(payload.discount_percent)
    sub.discount_expires_at = expires_at
    sub.retention_offer_used = True
    db.commit()
    db.refresh(sub)

    return RetentionDiscountResponse(
        status="applied",
        customer_id=customer_id,
        discount_percent=payload.discount_percent,
        duration_months=payload.duration_months,
        discount_expires_at=expires_at,
        reason=payload.reason,
        message=(
            f"Applied a {payload.discount_percent}% discount for "
            f"{payload.duration_months} months, expiring {expires_at.isoformat()}."
        ),
    )


@app.post(
    "/subscriptions/{customer_id}/cancel",
    response_model=CancelSubscriptionResponse,
    tags=["subscriptions"],
)
def cancel_subscription_endpoint(
    customer_id: str, payload: CancelSubscriptionRequest, db: Session = Depends(get_db)
) -> CancelSubscriptionResponse:
    if not payload.confirmed:
        raise HTTPException(status_code=400, detail="Cancellation requires explicit customer confirmation.")

    sub = _get_subscription_or_404(db, customer_id)
    if sub.status == "cancelled":
        raise HTTPException(status_code=409, detail=f"Subscription for {customer_id} is already cancelled.")

    sub.status = "cancelled"
    sub.cancelled_at = date.today()
    db.commit()
    db.refresh(sub)

    return CancelSubscriptionResponse(
        status="cancelled",
        customer_id=customer_id,
        cancelled_at=sub.cancelled_at,
        message="Subscription has been cancelled and will not renew.",
    )


@app.post("/subscriptions/{customer_id}/change-plan", response_model=ChangePlanResponse, tags=["subscriptions"])
def change_plan(
    customer_id: str, payload: ChangePlanRequest, db: Session = Depends(get_db)
) -> ChangePlanResponse:
    if payload.new_tier not in PLAN_PRICES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown tier '{payload.new_tier}'. Must be one of {list(PLAN_PRICES)}.",
        )

    sub = _get_subscription_or_404(db, customer_id)

    if payload.new_tier == sub.tier:
        raise HTTPException(status_code=400, detail=f"Customer is already on the {sub.tier} plan.")

    today = date.today()
    result = compute_plan_change(sub, payload.new_tier, today)
    delta = result["prorated_delta"]

    sub.tier = payload.new_tier
    sub.price_monthly = PLAN_PRICES[payload.new_tier]
    sub.monitor_limit = PLAN_LIMITS[payload.new_tier]

    if delta >= 0:
        # Downgrade: unused value becomes account credit, applied to the next invoice.
        sub.account_balance += delta
        immediate_charge = Decimal("0.00")
    else:
        # Upgrade: charge the prorated difference immediately.
        immediate_charge = -delta
        db.add(
            Invoice(
                invoice_id=_new_id("INV"),
                customer_id=customer_id,
                subscription_id=sub.subscription_id,
                amount=immediate_charge,
                currency="USD",
                status="paid",
                invoice_date=today,
                due_date=today,
                paid_at=today,
                failure_reason=None,
            )
        )

    db.commit()
    db.refresh(sub)

    return ChangePlanResponse(
        old_tier=result["old_tier"],
        new_tier=result["new_tier"],
        days_remaining=result["days_remaining"],
        days_in_cycle=result["days_in_cycle"],
        prorated_delta=delta,
        immediate_charge=immediate_charge,
        new_account_balance=sub.account_balance,
    )


@app.post("/subscriptions/{customer_id}/credit", response_model=CreditResponse, tags=["subscriptions"])
def apply_account_credit(
    customer_id: str, payload: CreditRequest, db: Session = Depends(get_db)
) -> CreditResponse:
    sub = _get_subscription_or_404(db, customer_id)
    sub.account_balance += payload.amount
    db.commit()
    db.refresh(sub)
    return CreditResponse(
        status="success",
        amount_credited=payload.amount,
        reason=payload.reason,
        new_account_balance=sub.account_balance,
    )


# ---------------------------------------------------------------------------
# Ticket CRUD
# ---------------------------------------------------------------------------


@app.get("/tickets/{ticket_id}", response_model=TicketRead, tags=["tickets"])
def get_ticket(ticket_id: str, db: Session = Depends(get_db)) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    return ticket


@app.post("/tickets", response_model=TicketRead, status_code=status.HTTP_201_CREATED, tags=["tickets"])
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db)) -> Ticket:
    if db.get(Customer, payload.customer_id) is None:
        raise HTTPException(status_code=404, detail=f"Customer {payload.customer_id} not found")

    ticket = Ticket(
        ticket_id=_new_id("TICK"),
        customer_id=payload.customer_id,
        category=payload.category,
        subtype=payload.subtype,
        subject=payload.subject,
        message=payload.message,
        status=payload.status,
        created_at=payload.created_at or date.today(),
        resolved_at=payload.resolved_at,
        resolution_notes=payload.resolution_notes,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


@app.patch("/tickets/{ticket_id}", response_model=TicketRead, tags=["tickets"])
def update_ticket(ticket_id: str, payload: TicketUpdate, db: Session = Depends(get_db)) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")

    updates = payload.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(ticket, field_name, value)

    if payload.status == "resolved" and "resolved_at" not in updates:
        ticket.resolved_at = date.today()
    elif payload.status is not None and payload.status != "resolved" and "resolved_at" not in updates:
        ticket.resolved_at = None

    db.commit()
    db.refresh(ticket)
    return ticket


@app.get("/tickets", response_model=list[TicketSummary], tags=["tickets"])
def get_recent_tickets(
    customer_id: str = Query(...),
    category: Optional[str] = Query(None),
    days: int = Query(3, ge=1, le=30, description="How many days back to look"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> list[Ticket]:
    """Recent tickets for one customer. Used by the agent for per-customer dedup."""
    cutoff_date = date.today() - timedelta(days=days)

    query = db.query(Ticket).filter(
        Ticket.customer_id == customer_id,
        Ticket.created_at >= cutoff_date,
    )
    if category:
        query = query.filter(Ticket.category == category)

    return query.order_by(Ticket.created_at.desc()).limit(limit).all()


# ---------------------------------------------------------------------------
# Human escalation queue
# ---------------------------------------------------------------------------


@app.post(
    "/escalations",
    response_model=EscalationRead,
    status_code=status.HTTP_201_CREATED,
    tags=["escalations"],
)
def create_escalation(payload: EscalationCreate, db: Session = Depends(get_db)) -> Escalation:
    if db.get(Customer, payload.customer_id) is None:
        raise HTTPException(status_code=404, detail=f"Customer {payload.customer_id} not found")
    if payload.ticket_id is not None and db.get(Ticket, payload.ticket_id) is None:
        raise HTTPException(status_code=404, detail=f"Ticket {payload.ticket_id} not found")

    escalation = Escalation(
        escalation_id=_new_id("ESC"),
        customer_id=payload.customer_id,
        ticket_id=payload.ticket_id,
        category=payload.category,
        confidence=payload.confidence,
        reasoning=payload.reasoning,
        proposed_action=payload.proposed_action,
        conversation_summary=payload.conversation_summary,
        status="pending",
        created_at=date.today(),
    )
    db.add(escalation)
    db.commit()
    db.refresh(escalation)
    return escalation


@app.get("/escalations", response_model=list[EscalationRead], tags=["escalations"])
def list_escalations(
    status_filter: str | None = Query(default="pending", alias="status"),
    customer_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[Escalation]:
    statement = select(Escalation).order_by(Escalation.created_at.desc())
    if status_filter is not None:
        statement = statement.where(Escalation.status == status_filter)
    if customer_id is not None:
        statement = statement.where(Escalation.customer_id == customer_id)
    return list(db.scalars(statement))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)