"""Long-term degradation history (L4-05) of one feature for a component.

The history keeps every window of every lifecycle. Maintenance that keeps the lifecycle (lubrication,
adjustment, partial repair) keeps the history continuous and is reported as a step: the change of the
feature across the event. A replacement starts a new segment, and deviations in each segment are
measured only against that lifecycle's own verified healthy reference (per regime where the reference
has enough windows of that regime); a lifecycle without one gets no deviations rather than borrowing
its predecessor's.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

from app.equipment.schemas import MaintenanceEvent, MaintenanceEventType
from app.monitoring.baselines.adaptive import ALPHA, adaptive_track
from app.monitoring.baselines.stats import deviation
from app.monitoring.schemas import (
    Baseline,
    DegradationHistory,
    DegradationPoint,
    DegradationSegment,
    FeatureVector,
    MaintenanceStep,
)

STEP_WINDOWS = 8  # windows on each side of a maintenance event used for its step


def _median(x: Sequence[float]) -> float | None:
    return float(np.median(x)) if len(x) else None


def degradation_history(
    component_id: str,
    feature: str,
    vectors: Sequence[FeatureVector],
    references: Mapping[str, Baseline],
    events: Sequence[MaintenanceEvent] = (),
    alpha: float = ALPHA,
    step_windows: int = STEP_WINDOWS,
) -> DegradationHistory:
    """``references`` maps lifecycle id to its verified healthy reference (missing: none verified)."""
    mine = sorted((v for v in vectors if v.component_id == component_id), key=lambda v: v.window.start)
    refs = {v.feature_ref for v in mine}
    if len(refs) > 1:
        raise ValueError("vectors of one feature set version are needed")
    for lc, ref in references.items():
        if ref.lifecycle_id != lc or ref.component_id != component_id:
            raise ValueError(f"reference {ref.baseline_id} does not belong to lifecycle '{lc}'")
    track = {p.window_end: p for p in adaptive_track(mine, feature, alpha)}
    segments: list[DegradationSegment] = []
    for v in mine:
        x = v.values.get(feature)
        if x is None:
            continue
        if not segments or segments[-1].lifecycle_id != v.lifecycle_id:
            ref = references.get(v.lifecycle_id)
            segments.append(
                DegradationSegment(
                    lifecycle_id=v.lifecycle_id,
                    reference_baseline_id=ref.baseline_id if ref else None,
                    points=[],
                )
            )
        ref = references.get(v.lifecycle_id)
        stats = None
        if ref is not None:  # the window's own regime when the reference has it, else the whole period
            stats = ref.regime_stats.get(v.regime_id or "", {}).get(feature) or ref.stats.get(feature)
        segments[-1].points.append(
            DegradationPoint(
                window=v.window,
                lifecycle_id=v.lifecycle_id,
                regime_id=v.regime_id,
                value=x,
                deviation=deviation(x, stats) if stats else None,
                adaptive_mean=track[v.window.end].mean,
            )
        )
    points = [p for s in segments for p in s.points]
    steps = []
    for e in sorted(events, key=lambda e: e.performed_at):
        if e.component_id != component_id or e.type in (
            MaintenanceEventType.REPLACEMENT,
            MaintenanceEventType.INSPECTION,
        ):
            continue
        before = [
            p.value for p in points if p.lifecycle_id == e.lifecycle_id and p.window.end <= e.performed_at
        ]
        after = [
            p.value for p in points if p.lifecycle_id == e.lifecycle_id and p.window.start >= e.performed_at
        ]
        b, a = _median(before[-step_windows:]), _median(after[:step_windows])
        steps.append(
            MaintenanceStep(
                event_id=e.event_id,
                type=e.type.value,
                at=e.performed_at,
                lifecycle_id=e.lifecycle_id,
                before=b,
                after=a,
                change=a - b if a is not None and b is not None else None,
            )
        )
    return DegradationHistory(
        component_id=component_id,
        feature=feature,
        feature_ref=refs.pop() if refs else "",
        segments=segments,
        steps=steps,
        is_simulated=any(v.is_simulated for v in mine),
    )
