"""Feature store: published feature schemas and computed feature vectors (L4-04, GEN-06).

A schema version is registered once; registering a different definition under the same
``feature_set@version`` is refused, so stored vectors always match the schema their ref names.
Vectors are keyed by component, feature ref and window start. Saving the same vector again is a
no-op; saving different values for an existing key is refused, since features are deterministic for
a given version and window.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base
from app.equipment.lifecycle import _aware
from app.monitoring.features.definitions import FEATURE_SETS
from app.monitoring.schemas import FeatureSchema, FeatureVector


class FeatureConflictError(ValueError):
    pass


class FeatureSchemaRecord(Base):
    __tablename__ = "feature_schemas"

    ref: Mapped[str] = mapped_column(String(80), primary_key=True)
    component_type: Mapped[str] = mapped_column(String(32), nullable=False)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FeatureVectorRecord(Base):
    __tablename__ = "feature_vectors"
    __table_args__ = (
        UniqueConstraint("component_id", "feature_ref", "window_start", name="uq_feature_vector"),
    )

    vector_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    component_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    lifecycle_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    regime_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    regime_status: Mapped[str] = mapped_column(String(16), nullable=False)
    catalog_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    feature_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_signals: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    values: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_simulated: Mapped[bool] = mapped_column(nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def to_model(self) -> FeatureVector:
        return FeatureVector(
            component_id=self.component_id,
            lifecycle_id=self.lifecycle_id,
            regime_id=self.regime_id,
            regime_status=self.regime_status,
            catalog_id=self.catalog_id,
            feature_ref=self.feature_ref,
            window={"start": _aware(self.window_start), "end": _aware(self.window_end)},
            source_signals=list(self.source_signals),
            values=dict(self.values),
            is_simulated=self.is_simulated,
        )


def _same(a: FeatureVector, b: FeatureVector) -> bool:
    return a.model_dump(mode="json") == b.model_dump(mode="json")


class FeatureStore:
    def __init__(self, session: Session):
        self.session = session

    def register(self, schema: FeatureSchema, now: datetime | None = None) -> None:
        rec = self.session.get(FeatureSchemaRecord, schema.ref)
        definition = schema.model_dump(mode="json")
        if rec is not None:
            if rec.definition != definition:
                raise FeatureConflictError(f"'{schema.ref}' is already published with another definition")
            return
        self.session.add(
            FeatureSchemaRecord(
                ref=schema.ref,
                component_type=schema.component_type,
                definition=definition,
                registered_at=now or datetime.now(UTC),
            )
        )
        self.session.flush()

    def register_all(self) -> None:
        for schema in FEATURE_SETS.values():
            self.register(schema)

    def schema(self, ref: str) -> FeatureSchema:
        rec = self.session.get(FeatureSchemaRecord, ref)
        if rec is None:
            raise KeyError(f"feature schema '{ref}' is not registered")
        return FeatureSchema.model_validate(rec.definition)

    def save(self, vectors: Sequence[FeatureVector], now: datetime | None = None) -> int:
        """Store vectors; returns how many were new."""
        now = now or datetime.now(UTC)
        added = 0
        for v in vectors:
            schema = self.schema(v.feature_ref)
            if set(v.values) != {f.name for f in schema.features}:
                raise FeatureConflictError(f"values do not match the features of '{v.feature_ref}'")
            existing = self.session.scalar(
                select(FeatureVectorRecord).where(
                    FeatureVectorRecord.component_id == v.component_id,
                    FeatureVectorRecord.feature_ref == v.feature_ref,
                    FeatureVectorRecord.window_start == v.window.start,
                )
            )
            if existing is not None:
                if not _same(existing.to_model(), v):
                    raise FeatureConflictError(
                        f"a different vector exists for {v.component_id} {v.feature_ref} {v.window.start}"
                    )
                continue
            self.session.add(
                FeatureVectorRecord(
                    vector_id=f"FV-{uuid.uuid4().hex[:16]}",
                    component_id=v.component_id,
                    lifecycle_id=v.lifecycle_id,
                    regime_id=v.regime_id,
                    regime_status=v.regime_status,
                    catalog_id=v.catalog_id,
                    feature_ref=v.feature_ref,
                    window_start=v.window.start,
                    window_end=v.window.end,
                    source_signals=v.source_signals,
                    values=v.values,
                    is_simulated=v.is_simulated,
                    computed_at=now,
                )
            )
            added += 1
        self.session.flush()
        return added

    def vectors(
        self,
        component_id: str,
        feature_ref: str | None = None,
        lifecycle_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[FeatureVector]:
        stmt = select(FeatureVectorRecord).where(FeatureVectorRecord.component_id == component_id)
        if feature_ref:
            stmt = stmt.where(FeatureVectorRecord.feature_ref == feature_ref)
        if lifecycle_id:
            stmt = stmt.where(FeatureVectorRecord.lifecycle_id == lifecycle_id)
        if start:
            stmt = stmt.where(FeatureVectorRecord.window_start >= start)
        if end:
            stmt = stmt.where(FeatureVectorRecord.window_end <= end)
        return [r.to_model() for r in self.session.scalars(stmt.order_by(FeatureVectorRecord.window_start))]
