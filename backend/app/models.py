"""
SQLAlchemy 2.0 models for the Pulsecheck mock CRM.

Belongs at: backend/app/models.py

The seeded entities are Customer, Subscription, Ticket, and KnownIncident.
Invoice, Refund, and Escalation are included because the build plan specifies
those CRM endpoints even though the supplied seed_data.py does not yet contain
rows for them.

The ISODate type accepts both ISO date strings (as used by seed_data.py) and
Python date objects, so seed rows can be passed directly to model constructors.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class ISODate(TypeDecorator[date]):
    """SQLite-friendly date type that also accepts ``YYYY-MM-DD`` strings."""

    impl = Date
    cache_ok = True

    def process_bind_param(self, value: date | str | None, dialect: Any) -> date | None:
        if value is None or isinstance(value, date):
            return value
        if isinstance(value, str):
            return date.fromisoformat(value)
        raise TypeError(f"Expected date, ISO date string, or None; got {type(value)!r}")

    def process_result_value(self, value: date | str | None, dialect: Any) -> date | None:
        if value is None or isinstance(value, date):
            return value
        if isinstance(value, str):
            return date.fromisoformat(value)
        return value


class Base(DeclarativeBase):
    """Declarative base for all mock CRM tables."""


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(160), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(120), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    signup_date: Mapped[date] = mapped_column(ISODate, nullable=False)
    tier: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    account_status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    subscription: Mapped[Subscription | None] = relationship(
        back_populates="customer",
        uselist=False,
        cascade="all, delete-orphan",
    )
    tickets: Mapped[list[Ticket]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
    )
    invoices: Mapped[list[Invoice]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
    )
    refunds: Mapped[list[Refund]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
    )
    escalations: Mapped[list[Escalation]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    subscription_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.customer_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    monitor_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    monitors_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_monthly: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    created_at: Mapped[date] = mapped_column(ISODate, nullable=False)
    next_billing_date: Mapped[date | None] = mapped_column(ISODate, nullable=True)
    trial_end_date: Mapped[date | None] = mapped_column(ISODate, nullable=True)
    cancelled_at: Mapped[date | None] = mapped_column(ISODate, nullable=True)
    failed_payment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payment_method_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)

    customer: Mapped[Customer] = relationship(back_populates="subscription")
    invoices: Mapped[list[Invoice]] = relationship(back_populates="subscription")


class Invoice(Base):
    """Invoice history used by the billing agent's CRM endpoint."""

    __tablename__ = "invoices"

    invoice_id: Mapped[str] = mapped_column(String(24), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.customer_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscription_id: Mapped[str | None] = mapped_column(
        ForeignKey("subscriptions.subscription_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    invoice_date: Mapped[date] = mapped_column(ISODate, nullable=False)
    due_date: Mapped[date | None] = mapped_column(ISODate, nullable=True)
    paid_at: Mapped[date | None] = mapped_column(ISODate, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    customer: Mapped[Customer] = relationship(back_populates="invoices")
    subscription: Mapped[Subscription | None] = relationship(back_populates="invoices")


class Ticket(Base):
    __tablename__ = "tickets"

    ticket_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.customer_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    subtype: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(240), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    created_at: Mapped[date] = mapped_column(ISODate, nullable=False, index=True)
    resolved_at: Mapped[date | None] = mapped_column(ISODate, nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    customer: Mapped[Customer] = relationship(back_populates="tickets")
    refunds: Mapped[list[Refund]] = relationship(back_populates="ticket")
    escalations: Mapped[list[Escalation]] = relationship(back_populates="ticket")


class KnownIncident(Base):
    __tablename__ = "known_incidents"

    incident_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    affected_component: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    started_at: Mapped[date] = mapped_column(ISODate, nullable=False)
    resolved_at: Mapped[date | None] = mapped_column(ISODate, nullable=True)
    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    customer_facing_note: Mapped[str] = mapped_column(Text, nullable=False)


class Refund(Base):
    """Refund requests and their approval state.

    The application service should enforce the project rule that refunds under
    $100 can be auto-approved while larger refunds require human review.
    """

    __tablename__ = "refunds"

    refund_id: Mapped[str] = mapped_column(String(24), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.customer_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticket_id: Mapped[str | None] = mapped_column(
        ForeignKey("tickets.ticket_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    created_at: Mapped[date] = mapped_column(ISODate, nullable=False)
    processed_at: Mapped[date | None] = mapped_column(ISODate, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    customer: Mapped[Customer] = relationship(back_populates="refunds")
    ticket: Mapped[Ticket | None] = relationship(back_populates="refunds")


class Escalation(Base):
    """Human-queue item created when the agent cannot safely resolve a ticket."""

    __tablename__ = "escalations"

    escalation_id: Mapped[str] = mapped_column(String(24), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.customer_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticket_id: Mapped[str | None] = mapped_column(
        ForeignKey("tickets.ticket_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_action: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    conversation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[date] = mapped_column(ISODate, nullable=False)
    resolved_at: Mapped[date | None] = mapped_column(ISODate, nullable=True)

    customer: Mapped[Customer] = relationship(back_populates="escalations")
    ticket: Mapped[Ticket | None] = relationship(back_populates="escalations")


# Useful indexes for the CRM list/filter endpoints.
Index("ix_tickets_customer_status", Ticket.customer_id, Ticket.status)
Index("ix_incidents_component_status", KnownIncident.affected_component, KnownIncident.status)


# Exported names make imports explicit in backend/app/main.py and seed scripts.
__all__ = [
    "Base",
    "Customer",
    "Subscription",
    "Invoice",
    "Ticket",
    "KnownIncident",
    "Refund",
    "Escalation",
    "ISODate",
]


if __name__ == "__main__":
    print("Mapped tables:", ", ".join(Base.metadata.tables))
