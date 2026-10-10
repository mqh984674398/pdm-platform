"""Append-only audit log for configuration changes and approvals (SEC-02)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import AwareDatetime
from sqlalchemy import JSON, DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base
from app.core.schemas import ContractModel
from app.core.security import Principal


class AuditRecord(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    object_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class AuditEntry(ContractModel):
    at: AwareDatetime
    actor: str
    actor_role: str
    action: str
    object_type: str
    object_id: str
    details: dict[str, Any]


def record(
    session: Session, who: Principal, action: str, object_type: str, object_id: str, **details: Any
) -> None:
    """Add an audit row in the caller's transaction, so the change and its record commit together."""
    session.add(
        AuditRecord(
            at=datetime.now(UTC),
            actor=who.user_id,
            actor_role=who.role.value,
            action=action,
            object_type=object_type,
            object_id=object_id,
            details=details,
        )
    )


def entries(
    session: Session, object_type: str | None = None, object_id: str | None = None
) -> list[AuditEntry]:
    stmt = select(AuditRecord).order_by(AuditRecord.id)
    if object_type:
        stmt = stmt.where(AuditRecord.object_type == object_type)
    if object_id:
        stmt = stmt.where(AuditRecord.object_id == object_id)
    out = []
    for r in session.scalars(stmt):
        at = r.at if r.at.tzinfo else r.at.replace(tzinfo=UTC)  # SQLite drops the zone
        out.append(
            AuditEntry(
                at=at,
                actor=r.actor,
                actor_role=r.actor_role,
                action=r.action,
                object_type=r.object_type,
                object_id=r.object_id,
                details=r.details,
            )
        )
    return out
