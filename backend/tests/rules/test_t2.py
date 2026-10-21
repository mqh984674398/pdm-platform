"""D-045: Hotelling T² against the healthy reference windows (unsupervised)."""

from datetime import UTC, datetime, timedelta

import numpy as np

from app.core.schemas import TimeWindow
from app.monitoring.anomaly import t2
from app.monitoring.schemas import FeatureVector

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def vecs(rows, start=0):
    def win(i):
        t = T0 + timedelta(hours=start + i)
        return TimeWindow(start=t, end=t + timedelta(hours=1))

    return [
        FeatureVector(
            component_id="C",
            lifecycle_id="L",
            regime_id=None,
            regime_status="KNOWN",
            catalog_id=None,
            feature_ref="f@1",
            window=win(i),
            source_signals=[],
            values={"a": float(r[0]), "b": float(r[1])},
            is_simulated=True,
        )
        for i, r in enumerate(rows)
    ]


def healthy(n, seed=0):
    rng = np.random.default_rng(seed)
    base = rng.normal(size=(n, 1))
    return np.hstack(
        [10 + base + 0.3 * rng.normal(size=(n, 1)), 5 + 0.5 * base + 0.3 * rng.normal(size=(n, 1))]
    )


def test_healthy_windows_do_not_flag_and_shifted_ones_do():
    ref = vecs(healthy(60))
    ok = t2.assess(ref, vecs(healthy(2, seed=9), 100), ["a", "b"])
    assert ok.usable and not ok.flagged and ok.n_reference == 60
    shifted = vecs([[16.0, 2.0], [16.2, 2.1]], 100)  # off the healthy correlation structure
    bad = t2.assess(ref, shifted, ["a", "b"])
    assert bad.usable and bad.flagged and bad.value > bad.limit


def test_one_bad_window_is_not_enough_and_too_few_reference_is_not_evaluated():
    ref = vecs(healthy(60))
    mixed = vecs([[10.0, 5.0], [16.0, 2.0]], 100)
    assert not t2.assess(ref, mixed, ["a", "b"]).flagged
    few = t2.assess(vecs(healthy(8)), mixed, ["a", "b"])
    assert not few.usable and few.reason == "TOO_FEW_REFERENCE"  # never a verdict from a thin reference
    assert t2.assess(ref, mixed, []).reason == "NO_FEATURES"
