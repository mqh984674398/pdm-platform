"""Verified healthy reference (L4-05, L4-06, OPT-05) and stored baselines.

A verified healthy reference is created only by ``verify``: an engineer names a lifecycle, feature
set, optional regime and period that is known to be healthy, with a comment. Its statistics come from
the stored feature vectors of exactly that period and are frozen. Nothing else writes one: new data,
adaptive baselines and degradation tracking never change it, so normal aging stays visible against
it. A new verification supersedes the previous reference for the same key; both are kept. Every
verification is audited.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from scipy.stats import theilslopes
from sqlalchemy import JSON, DateTime, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.audit import record as audit
from app.core.db import Base
from app.core.schemas import LocalizedText, ResultMeta, TimeWindow
from app.core.security import Principal, Role
from app.equipment.lifecycle import _aware
from app.monitoring.baselines.stats import MIN_VALUES, feature_stats, spread
from app.monitoring.features.store import FeatureStore
from app.monitoring.rules.definitions import DEFAULT_RULES
from app.monitoring.rules.engine import component_type
from app.monitoring.schemas import (
    Baseline,
    BaselineKind,
    BaselineVerification,
    FeatureStats,
    FeatureVector,
    RuleKind,
)

MIN_VECTORS = 5
MODEL_VERSION = "verified-reference@1.0.0"
DRIFT_SPREADS = 1.5  # drift inside the period, in reference spreads, that suggests it was not steady
FEW_WINDOWS = 10  # fewer windows give a spread estimate too rough for fixed deviation thresholds


def quality_warnings(vectors: list[FeatureVector], stats: dict[str, FeatureStats]) -> list[LocalizedText]:
    """Notes on a candidate reference period (D-040). They never block a verification: the engineer
    decides. A reference taken while the component was already degrading hides that degradation."""
    ctype = component_type(vectors[0].feature_ref)
    # the first feature of each statistical rule of this type (regime-normalized where there is one)
    health = {
        r.features[0]
        for r in DEFAULT_RULES.rules
        if r.kind == RuleKind.STATISTICAL and ctype in r.component_types
    }
    out = []
    if len(vectors) < FEW_WINDOWS:
        out.append(
            LocalizedText(
                zh=f"参考期仅 {len(vectors)} 个窗口，偏差尺度估计粗糙，建议至少 {FEW_WINDOWS} 个",
                en=f"Only {len(vectors)} windows in the period; the spread is rough, "
                f"{FEW_WINDOWS} or more are advised",
            )
        )
    t0 = min(v.window.start for v in vectors)
    for f in sorted(health & stats.keys()):
        pts = [
            ((v.window.start - t0).total_seconds() / 86400, v.values[f])
            for v in vectors
            if v.values.get(f) is not None
        ]
        span = max(t for t, _ in pts) - min(t for t, _ in pts) if len(pts) >= MIN_VALUES else 0.0
        if span <= 0:
            continue
        slope = float(theilslopes([y for _, y in pts], [t for t, _ in pts])[0])
        drift = slope * span / spread(stats[f])
        if abs(drift) >= DRIFT_SPREADS:
            out.append(
                LocalizedText(
                    zh=f"参考期内 {f} 已漂移 {drift:+.1f} 个标准差，该时段可能并非稳定健康，请复核后再确认",
                    en=f"{f} drifts {drift:+.1f} spreads inside the period; it may not be steady healthy, "
                    "review before verifying",
                )
            )
    return out


class BaselineError(ValueError):
    pass


class BaselinePermissionError(PermissionError):
    pass


class BaselineRecord(Base):
    __tablename__ = "baselines"

    baseline_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    component_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    lifecycle_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    regime_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    feature_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stats: Mapped[dict] = mapped_column(JSON, nullable=False)
    regime_stats: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    verified_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comment: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    superseded_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, nullable=False)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    def to_model(self) -> Baseline:
        return Baseline(
            baseline_id=self.baseline_id,
            kind=BaselineKind(self.kind),
            component_id=self.component_id,
            lifecycle_id=self.lifecycle_id,
            regime_id=self.regime_id,
            feature_ref=self.feature_ref,
            window=TimeWindow(start=_aware(self.window_start), end=_aware(self.window_end)),
            stats={k: FeatureStats.model_validate(v) for k, v in self.stats.items()},
            regime_stats={
                r: {k: FeatureStats.model_validate(v) for k, v in st.items()}
                for r, st in self.regime_stats.items()
            },
            verified_by=self.verified_by,
            verified_at=_aware(self.verified_at),
            comment=self.comment,
            superseded_by=self.superseded_by,
            warnings=[LocalizedText.model_validate(w) for w in self.warnings or []],
            meta=ResultMeta.model_validate(self.meta),
        )


def _dump(by_regime: dict[str, dict[str, FeatureStats]]) -> dict:
    return {r: {k: x.model_dump(mode="json") for k, x in st.items()} for r, st in by_regime.items()}


class BaselineService:
    def __init__(self, session: Session):
        self.session = session
        self.features = FeatureStore(session)

    def _current(
        self,
        kind: BaselineKind,
        component_id: str,
        lifecycle_id: str,
        feature_ref: str,
        regime_id: str | None,
    ):
        stmt = select(BaselineRecord).where(
            BaselineRecord.kind == kind.value,
            BaselineRecord.component_id == component_id,
            BaselineRecord.lifecycle_id == lifecycle_id,
            BaselineRecord.feature_ref == feature_ref,
            BaselineRecord.superseded_by.is_(None),
            BaselineRecord.regime_id.is_(None)
            if regime_id is None
            else BaselineRecord.regime_id == regime_id,
        )
        return self.session.scalar(stmt)

    def verified(
        self, component_id: str, lifecycle_id: str, feature_ref: str, regime_id: str | None = None
    ) -> Baseline | None:
        rec = self._current(BaselineKind.VERIFIED_HEALTHY, component_id, lifecycle_id, feature_ref, regime_id)
        return rec.to_model() if rec else None

    def baselines(self, component_id: str, include_superseded: bool = False) -> list[Baseline]:
        stmt = select(BaselineRecord).where(BaselineRecord.component_id == component_id)
        if not include_superseded:
            stmt = stmt.where(BaselineRecord.superseded_by.is_(None))
        stmt = stmt.order_by(BaselineRecord.window_start, BaselineRecord.baseline_id)
        return [r.to_model() for r in self.session.scalars(stmt)]

    def verify(self, req: BaselineVerification, who: Principal, now: datetime | None = None) -> Baseline:
        if not who.at_least(Role.ENGINEER):
            raise BaselinePermissionError("verifying a healthy reference requires an engineer")
        if not req.comment.strip():
            raise BaselineError("a verification needs a comment explaining why the period is healthy")
        now = now or datetime.now(UTC)
        if req.window.end > now:
            raise BaselineError("a healthy reference cannot include the future")
        vectors = [
            v
            for v in self.features.vectors(
                req.component_id, req.feature_ref, req.lifecycle_id, req.window.start, req.window.end
            )
            if req.regime_id is None or v.regime_id == req.regime_id
        ]
        if len(vectors) < MIN_VECTORS:
            raise BaselineError(
                f"the period has {len(vectors)} feature windows for this lifecycle; "
                f"at least {MIN_VECTORS} are needed"
            )
        stats = feature_stats(vectors, MIN_VALUES)
        if not stats:
            raise BaselineError("no feature has enough values in the period")
        regimes = sorted({v.regime_id for v in vectors if v.regime_id})
        by_regime = {
            r: st
            for r in regimes
            if (st := feature_stats([v for v in vectors if v.regime_id == r], MIN_VALUES))
        }
        catalogs = sorted({v.catalog_id for v in vectors if v.catalog_id})
        sim = any(v.is_simulated for v in vectors)
        warnings = quality_warnings(vectors, stats)
        bid = f"BL-{uuid.uuid4().hex[:16]}"
        meta = ResultMeta(
            model_version=MODEL_VERSION,
            feature_version=req.feature_ref,
            config_version=",".join(catalogs) or "no-regime-catalog",
            computed_at=now,
            data_window=req.window,
            is_simulated=sim,
        )
        previous = self._current(
            BaselineKind.VERIFIED_HEALTHY, req.component_id, req.lifecycle_id, req.feature_ref, req.regime_id
        )
        if previous is not None:
            previous.superseded_by = bid
        rec = BaselineRecord(
            baseline_id=bid,
            kind=BaselineKind.VERIFIED_HEALTHY.value,
            component_id=req.component_id,
            lifecycle_id=req.lifecycle_id,
            regime_id=req.regime_id,
            feature_ref=req.feature_ref,
            window_start=req.window.start,
            window_end=req.window.end,
            stats={k: s.model_dump(mode="json") for k, s in stats.items()},
            regime_stats=_dump(by_regime),
            verified_by=who.user_id,
            verified_at=now,
            comment=req.comment.strip(),
            meta=meta.model_dump(mode="json"),
            warnings=[w.model_dump() for w in warnings],
        )
        self.session.add(rec)
        audit(
            self.session,
            who,
            "baseline.verify",
            "baseline",
            bid,
            component_id=req.component_id,
            lifecycle_id=req.lifecycle_id,
            feature_ref=req.feature_ref,
            regime_id=req.regime_id,
            window_start=req.window.start.isoformat(),
            window_end=req.window.end.isoformat(),
            vectors=len(vectors),
            supersedes=previous.baseline_id if previous else None,
            warnings=[w.en for w in warnings],
            comment=req.comment.strip(),
        )
        self.session.flush()
        return rec.to_model()

    def save_snapshot(self, baseline: Baseline) -> Baseline:
        """Store an adaptive or degradation-history snapshot. Never a verified reference."""
        if baseline.kind == BaselineKind.VERIFIED_HEALTHY:
            raise BaselineError("a verified healthy reference is created only by verify")
        previous = self._current(
            baseline.kind,
            baseline.component_id,
            baseline.lifecycle_id,
            baseline.feature_ref,
            baseline.regime_id,
        )
        if previous is not None:
            previous.superseded_by = baseline.baseline_id
        self.session.add(
            BaselineRecord(
                baseline_id=baseline.baseline_id,
                kind=baseline.kind.value,
                component_id=baseline.component_id,
                lifecycle_id=baseline.lifecycle_id,
                regime_id=baseline.regime_id,
                feature_ref=baseline.feature_ref,
                window_start=baseline.window.start,
                window_end=baseline.window.end,
                stats={k: s.model_dump(mode="json") for k, s in baseline.stats.items()},
                regime_stats=_dump(baseline.regime_stats),
                comment=baseline.comment,
                meta=baseline.meta.model_dump(mode="json"),
            )
        )
        self.session.flush()
        return baseline
