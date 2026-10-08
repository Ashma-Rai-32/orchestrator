import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from staffroom_api.db.base import Base


class Tenant(Base):
    """A customer organisation. Every other table will reference one."""

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Employee(Base):
    """An AI employee hired by a tenant. Skills are catalog keys, merged at run time."""

    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    skills: Mapped[list[str]] = mapped_column(ARRAY(String(100)))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Run(Base):
    """One attempt by a tenant's team to reach a goal."""

    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    goal: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))  # queued | running | succeeded | failed
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Event(Base):
    """Append-only log of what happened in a run (see agents/events.py for types)."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(50))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InboxItem(Base):
    """A question an employee asked the admin (a paused LangGraph interrupt)."""

    __tablename__ = "inbox_items"
    __table_args__ = (UniqueConstraint("run_id", "question_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(String(100))  # LangGraph interrupt id
    employee: Mapped[str] = mapped_column(String(200))
    question: Mapped[str] = mapped_column(Text)
    # Set when the employee needs a credential: the answer goes to the secret store
    # under this name (ADR-0009) and is never written to this table.
    secret_name: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(20), server_default="question")  # | approval
    preview_url: Mapped[str | None] = mapped_column(Text)  # approval: the site to review
    status: Mapped[str] = mapped_column(String(20), server_default="open")  # open | answered
    # Plain answers only; for secrets this holds "stored as NAME", never the value.
    answer: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
