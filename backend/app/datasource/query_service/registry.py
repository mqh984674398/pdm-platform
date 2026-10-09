"""Versioned, audited registry of approved query templates (L1-05, SEC-02)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.audit import record as audit
from app.core.db import Base
from app.core.security import Principal
from app.datasource.query_service.sql_guard import check_template_sql
from app.datasource.schemas import QueryTemplate, QueryTemplateAdminView, QueryTemplateSpec

ACTIVE, SUPERSEDED, RETIRED = "ACTIVE", "SUPERSEDED", "RETIRED"


class TemplateConflictError(ValueError):
    pass


class TemplateNotFoundError(LookupError):
    pass


class QueryTemplateRecord(Base):
    __tablename__ = "query_templates"
    __table_args__ = (UniqueConstraint("template_id", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    data_source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    spec: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    sql: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def to_spec(self) -> QueryTemplateSpec:
        return QueryTemplateSpec.model_validate(self.spec)

    def to_template(self) -> QueryTemplate:
        s = self.to_spec()
        return QueryTemplate(
            template_id=s.template_id,
            name=s.name,
            description=s.description,
            data_source_id=s.data_source_id,
            parameters=s.parameters,
            max_rows=s.max_rows,
            max_range_hours=s.max_range_hours,
            version=self.version,
        )

    def to_admin_view(self) -> QueryTemplateAdminView:
        at = self.created_at if self.created_at.tzinfo else self.created_at.replace(tzinfo=UTC)
        return QueryTemplateAdminView(
            **self.to_template().model_dump(), sql=self.sql, created_by=self.created_by, created_at=at
        )


def sql_hash(sql: str) -> str:
    return "sha256:" + hashlib.sha256(sql.encode("utf-8")).hexdigest()


class TemplateRegistry:
    def __init__(self, session: Session):
        self.session = session

    def active(self, template_id: str) -> QueryTemplateRecord:
        rec = self.session.scalar(
            select(QueryTemplateRecord).where(
                QueryTemplateRecord.template_id == template_id, QueryTemplateRecord.status == ACTIVE
            )
        )
        if rec is None:
            raise TemplateNotFoundError(template_id)
        return rec

    def list_active(self) -> list[QueryTemplateRecord]:
        return list(
            self.session.scalars(
                select(QueryTemplateRecord)
                .where(QueryTemplateRecord.status == ACTIVE)
                .order_by(QueryTemplateRecord.template_id)
            )
        )

    def history(self, template_id: str) -> list[QueryTemplateRecord]:
        return list(
            self.session.scalars(
                select(QueryTemplateRecord)
                .where(QueryTemplateRecord.template_id == template_id)
                .order_by(QueryTemplateRecord.version)
            )
        )

    def create(
        self, spec: QueryTemplateSpec, who: Principal, allowed_tables: set[str]
    ) -> QueryTemplateRecord:
        if self.history(spec.template_id):
            raise TemplateConflictError(f"template '{spec.template_id}' already exists")
        check_template_sql(spec.sql, {p.name for p in spec.parameters}, allowed_tables)
        rec = self._insert(spec, 1, who)
        audit(self.session, who, "template.create", "query_template", spec.template_id,
              version=1, sql_hash=sql_hash(spec.sql))  # fmt: skip
        return rec

    def update(
        self, spec: QueryTemplateSpec, who: Principal, allowed_tables: set[str]
    ) -> QueryTemplateRecord:
        current = self.active(spec.template_id)
        check_template_sql(spec.sql, {p.name for p in spec.parameters}, allowed_tables)
        before = current.to_spec().model_dump(mode="json")
        after = spec.model_dump(mode="json")
        changed = sorted(k for k in after if before.get(k) != after[k])
        if not changed:
            raise TemplateConflictError("no changes")
        current.status = SUPERSEDED
        self.session.flush()
        rec = self._insert(spec, current.version + 1, who)
        audit(self.session, who, "template.update", "query_template", spec.template_id,
              version=rec.version, previous_version=current.version, changed=changed,
              sql_hash_before=sql_hash(current.sql), sql_hash_after=sql_hash(spec.sql))  # fmt: skip
        return rec

    def retire(self, template_id: str, who: Principal) -> None:
        current = self.active(template_id)
        current.status = RETIRED
        audit(self.session, who, "template.retire", "query_template", template_id, version=current.version)

    def _insert(self, spec: QueryTemplateSpec, version: int, who: Principal) -> QueryTemplateRecord:
        rec = QueryTemplateRecord(
            template_id=spec.template_id,
            version=version,
            status=ACTIVE,
            data_source_id=spec.data_source_id,
            spec=spec.model_dump(mode="json"),
            sql=spec.sql,
            created_by=who.user_id,
            created_at=datetime.now(UTC),
        )
        self.session.add(rec)
        self.session.flush()
        return rec
