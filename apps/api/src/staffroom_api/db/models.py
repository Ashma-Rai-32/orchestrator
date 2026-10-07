import uuid
from datetime import datetime

from sqlalchemy import ARRAY, DateTime, ForeignKey, String, func, text
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
