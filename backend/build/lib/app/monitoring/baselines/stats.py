"""Descriptive statistics of feature values (L4-07)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from app.monitoring.schemas import FeatureStats, FeatureVector

MIN_VALUES = 5  # values a feature needs in the period before it gets reference statistics


def describe(x: Sequence[float]) -> FeatureStats:
    a = np.asarray(x, dtype=float)
    p05, p50, p95 = (float(q) for q in np.percentile(a, [5, 50, 95]))
    return FeatureStats(
        mean=float(a.mean()),
        std=float(a.std(ddof=1)) if a.size > 1 else 0.0,
        p05=p05,
        p50=p50,
        p95=p95,
        n=int(a.size),
    )


def feature_stats(vectors: Sequence[FeatureVector], min_values: int = MIN_VALUES) -> dict[str, FeatureStats]:
    names = sorted({k for v in vectors for k in v.values})
    out = {}
    for k in names:
        vals = [v.values[k] for v in vectors if v.values.get(k) is not None]
        if len(vals) >= min_values:
            out[k] = describe(vals)  # type: ignore[arg-type]
    return out


def spread(ref: FeatureStats) -> float:
    """Scale for deviations: the reference spread, floored so a near-constant reference does not
    turn tiny changes into huge deviations."""
    return max(ref.std, 0.01 * abs(ref.mean), 1e-9)


def deviation(value: float, ref: FeatureStats) -> float:
    return (value - ref.mean) / spread(ref)
