"""Compare a component's regime-normalized behavior before and after a maintenance event.

Only windows in a KNOWN regime count, and a regime is compared only when it appears both before
(at least ``min_pre_windows``) and after the event: a recipe that ran only on one side cannot show an
effect. The stabilization period right after the event is excluded. Per feature, the change is the
post-minus-pre median of the condition-normalized residual, averaged over compatible regimes weighted
by post windows. Larger torque and longer actuator durations are worse.

Outcome per feature: DETERIORATED (change >= effect), IMPROVED (change <= -effect; PARTIAL when the
post level is still >= elevated against the regime reference), NO_CHANGE, or UNKNOWN when fewer than
``min_post_windows`` comparable windows follow. The event's outcome is DETERIORATED if any feature
deteriorated, else PARTIAL, IMPROVED, NO_CHANGE in that order, else UNKNOWN.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

import numpy as np

from app.core.schemas import LocalizedText, TimeWindow
from app.equipment.cycles import CycleSignal
from app.equipment.regimes import assign_regimes
from app.equipment.schemas import (
    FeatureImpact,
    ImpactConfig,
    ImpactOutcome,
    MaintenanceImpact,
    RegimeAssignment,
    RegimeCatalog,
    RegimeComparison,
    RegimeStatus,
)
from app.equipment.state import Series, is_operation
from app.signals.schemas import PhysicalQuantity

Out = ImpactOutcome
PRIORITY = [Out.DETERIORATED, Out.PARTIAL, Out.IMPROVED, Out.NO_CHANGE]


def _t(zh: str, en: str) -> LocalizedText:
    return LocalizedText(zh=zh, en=en)


REASONS = {
    Out.IMPROVED: _t("维护后工况归一化指标改善", "Regime-normalized behavior improved after maintenance"),
    Out.PARTIAL: _t(
        "有改善，但仍明显高于工况基准，需复核", "Improved, but still well above the reference: review"
    ),
    Out.NO_CHANGE: _t("维护前后无明显变化", "No clear change after maintenance"),
    Out.DETERIORATED: _t("维护后指标变差，需复核", "Behavior got worse after maintenance: review"),
    Out.UNKNOWN: _t("维护前后可比工况数据不足", "Not enough data in comparable regimes before and after"),
}


def _residuals(
    assignments: Sequence[RegimeAssignment], health: set[str]
) -> dict[str, dict[str, list[float]]]:
    """feature id -> regime id -> normalized values."""
    out: dict[str, dict[str, list[float]]] = {}
    for a in assignments:
        if a.status != RegimeStatus.KNOWN or a.regime_id is None:
            continue
        for f in a.features:
            if f.normalized is not None and f.feature_id in health:
                out.setdefault(f.feature_id, {}).setdefault(a.regime_id, []).append(f.normalized)
    return out


def _feature(
    fid: str, pre: Mapping[str, list[float]], post: Mapping[str, list[float]], cfg: ImpactConfig
) -> FeatureImpact:
    regimes = [
        RegimeComparison(
            regime_id=r,
            pre_windows=len(pre[r]),
            post_windows=len(post[r]),
            pre_median=float(np.median(pre[r])),
            post_median=float(np.median(post[r])),
        )
        for r in sorted(set(pre) & set(post))
        if len(pre[r]) >= cfg.min_pre_windows
    ]
    n = sum(c.post_windows for c in regimes)
    if n < cfg.min_post_windows:
        return FeatureImpact(
            feature_id=fid, outcome=Out.UNKNOWN, change=None, post_level=None, regimes=regimes
        )
    change = sum((c.post_median - c.pre_median) * c.post_windows for c in regimes) / n
    level = float(np.median([x for c in regimes for x in post[c.regime_id]]))
    if change >= cfg.effect:
        outcome = Out.DETERIORATED
    elif change <= -cfg.effect:
        outcome = Out.PARTIAL if level >= cfg.elevated else Out.IMPROVED
    else:
        outcome = Out.NO_CHANGE
    return FeatureImpact(feature_id=fid, outcome=outcome, change=change, post_level=level, regimes=regimes)


def analyze_impact(
    series: Sequence[Series],
    component_id: str,
    event_time: datetime,
    catalog: RegimeCatalog,
    config: ImpactConfig | None = None,
    cycle_config: Mapping[str, CycleSignal] | None = None,
    post_hours: float | None = None,
) -> MaintenanceImpact:
    """``post_hours`` overrides ``validation_hours`` (the workflow extends validation while data is
    insufficient, up to ``max_validation_hours``)."""
    cfg = config or ImpactConfig()
    if catalog.learned_from.end > event_time:
        raise ValueError("the regime catalog must be learned before the maintenance event")
    pre = TimeWindow(start=event_time - timedelta(hours=cfg.pre_hours), end=event_time)
    post_start = event_time + timedelta(hours=cfg.stabilization_hours)
    post = TimeWindow(start=post_start, end=post_start + timedelta(hours=post_hours or cfg.validation_hours))
    # health-bearing features only: speeds and intervals define the regime and are not compared
    health = {
        f"{s.signal.signal_id}:cruise"
        for s in series
        if s.component_id == component_id and s.signal.quantity == PhysicalQuantity.TORQUE
    }
    health |= {
        f"{s.signal.signal_id}:median" for s in series if s.component_id == component_id and is_operation(s)
    }
    before = [a for a in assign_regimes(series, pre, catalog, cycle_config) if a.end <= event_time]
    after = [a for a in assign_regimes(series, post, catalog, cycle_config) if a.start >= post_start]
    pre_r, post_r = _residuals(before, health), _residuals(after, health)
    features = [
        _feature(f, pre_r.get(f, {}), post_r.get(f, {}), cfg) for f in sorted(set(pre_r) | set(post_r))
    ]
    known = [f.outcome for f in features if f.outcome != Out.UNKNOWN]
    outcome = next((o for o in PRIORITY if o in known), Out.UNKNOWN)
    return MaintenanceImpact(
        component_id=component_id,
        event_time=event_time,
        pre=pre,
        post=post,
        catalog_id=catalog.catalog_id,
        config=cfg,
        outcome=outcome,
        features=features,
        reason=REASONS[outcome],
        is_simulated=any(s.is_simulated for s in series if s.component_id == component_id),
    )
