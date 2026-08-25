"""
Pulsecheck Mock CRM API.

Belongs at: backend/app/main.py

Run locally from this directory with:
    uvicorn main:app --reload

The service uses SQLite + SQLAlchemy and seeds the database once on startup
from seed_data.py. Set PULSECHECK_DATABASE_URL to use another SQLite URL, for
example: sqlite:///./pulsecheck.db
"""

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

try:  # Supports both `uvicorn app.main:app` and `uvicorn main:app`.
    from .models import (
        Base,
        Customer,
        Escalation,
        Invoice,
        KnownIncident,
        Refund,
        Subscription,
        Ticket,
    )
    from routes.seed_data import CUSTOMERS, KNOWN_INCIDENTS, SUBSCRIPTIONS, TICKETS
except ImportError:  # pragma: no cover - used when running from backend/app.
    from models import (
        Base,
        Customer,
        Escalation,
        Invoice,
        KnownIncident,
        Refund,
        Subscription,
        Ticket,
    )
    from routes.seed_data import CUSTOMERS, KNOWN_INCIDENTS, SUBSCRIPTIONS, TICKETS


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
    status: str
    created_at: date
    next_billing_date: date | None
    trial_end_date: date | None
    cancelled_at: date | None
    failed_payment_count: int
    payment_method_last4: str | None


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


def seed_database() -> None:
    """Create tables and load seed_data.py exactly once for an empty database."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        already_seeded = db.scalar(select(Customer.customer_id).limit(1)) is not None
        if already_seeded:
            return

        db.add_all(Customer(**row) for row in CUSTOMERS)
        db.add_all(Subscription(**row) for row in SUBSCRIPTIONS)
        db.add_all(Ticket(**row) for row in TICKETS)
        db.add_all(KnownIncident(**row) for row in KNOWN_INCIDENTS)
        db.commit()


@app.on_event("startup")
def on_startup() -> None:
    seed_database()


# ---------------------------------------------------------------------------
# Health and lookup endpoints
# ---------------------------------------------------------------------------


@app.get("/", tags=["health"])
def root() -> dict[str, str]:
    return {"service": "Pulsecheck Mock CRM", "status": "ok"}


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/customers/{customer_id}", response_model=CustomerRead, tags=["customers"])
def get_customer(customer_id: str, db: Session = Depends(get_db)) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
    return customer


@app.get("/subscriptions/{customer_id}", response_model=SubscriptionRead, tags=["subscriptions"])
def get_subscription(customer_id: str, db: Session = Depends(get_db)) -> Subscription:
    subscription = db.scalar(
        select(Subscription).where(Subscription.customer_id == customer_id)
    )
    if subscription is None:
        raise HTTPException(status_code=404, detail=f"Subscription for {customer_id} not found")
    return subscription


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
    statement = select(KnownIncident).order_by(KnownIncident.started_at.desc())
    if status_filter is not None:
        statement = statement.where(KnownIncident.status == status_filter)
    return list(db.scalars(statement))


# ---------------------------------------------------------------------------
# Refunds: the explicit business guardrail
# ---------------------------------------------------------------------------


@app.post("/refunds", response_model=RefundRead, status_code=status.HTTP_201_CREATED, tags=["refunds"])
def issue_refund(payload: RefundCreate, db: Session = Depends(get_db)) -> RefundRead:
    if db.get(Customer, payload.customer_id) is None:
        raise HTTPException(status_code=404, detail=f"Customer {payload.customer_id} not found")
    if payload.ticket_id is not None and db.get(Ticket, payload.ticket_id) is None:
        raise HTTPException(status_code=404, detail=f"Ticket {payload.ticket_id} not found")

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
    db: Session = Depends(get_db),
) -> list[Escalation]:
    statement = select(Escalation).order_by(Escalation.created_at.desc())
    if status_filter is not None:
        statement = statement.where(Escalation.status == status_filter)
    return list(db.scalars(statement))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
