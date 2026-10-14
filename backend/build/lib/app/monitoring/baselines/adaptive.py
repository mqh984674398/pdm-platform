"""Adaptive operating baseline (L4-05): follows current behavior, including normal aging.

An exponentially weighted mean and spread of one feature, restarted at each lifecycle start. It is
computed from online observations and is never a verified healthy reference (OPT-05): nothing here can
create or change one.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from app.core.schemas import ResultMeta, TimeWindow
from app.monitoring.schemas import AdaptivePoint, Baseline, BaselineKind, FeatureStats, FeatureVector

ALPHA = 0.1  # weight of the newest window
MODEL_VERSION = "adaptive-ewma@1.0.0"


def adaptive_track(
    vectors: Sequence[FeatureVector], feature: str, alpha: float = ALPHA
) -> list[AdaptivePoint]:
    """Vectors in time order. Windows without the feature leave the baseline unchanged."""
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")
    out: list[AdaptivePoint] = []
    lc, mean, var, n = None, 0.0, 0.0, 0
    for v in sorted(vectors, key=lambda v: v.window.start):
        x = v.values.get(feature)
        if x is None:
            continue
        if v.lifecycle_id != lc:
            lc, mean, var, n = v.lifecycle_id, x, 0.0, 0
        else:
            d = x - mean
            mean += alpha * d
            var = (1 - alpha) * (var + alpha * d * d)
        n += 1
        out.append(AdaptivePoint(window_end=v.window.end, lifecycle_id=lc, mean=mean, std=var**0.5, n=n))
    return out


def adaptive_baseline(
    vectors: Sequence[FeatureVector], lifecycle_id: str, computed_at: datetime, alpha: float = ALPHA
) -> Baseline:
    """Snapshot of the adaptive baseline of every feature at the latest window of one lifecycle."""
    mine = sorted((v for v in vectors if v.lifecycle_id == lifecycle_id), key=lambda v: v.window.start)
    if not mine:
        raise ValueError(f"no feature windows for lifecycle '{lifecycle_id}'")
    refs = {v.feature_ref for v in mine}
    if len(refs) != 1:
        raise ValueError("vectors of one feature set version are needed")
    stats = {}
    for k in mine[0].values:
        track = adaptive_track(mine, k, alpha)
        if track:
            p = track[-1]
            stats[k] = FeatureStats(mean=p.mean, std=p.std, n=p.n)
    window = TimeWindow(start=mine[0].window.start, end=mine[-1].window.end)
    catalogs = sorted({v.catalog_id for v in mine if v.catalog_id})
    return Baseline(
        baseline_id=f"BL-{uuid.uuid4().hex[:16]}",
        kind=BaselineKind.ADAPTIVE,
        component_id=mine[0].component_id,
        lifecycle_id=lifecycle_id,
        regime_id=None,
        feature_ref=refs.pop(),
        window=window,
        stats=stats,
        meta=ResultMeta(
            model_version=f"{MODEL_VERSION}:alpha={alpha:g}",
            feature_version=mine[0].feature_ref,
            config_version=",".join(catalogs) or "no-regime-catalog",
            computed_at=computed_at,
            data_window=window,
            is_simulated=any(v.is_simulated for v in mine),
        ),
    )
