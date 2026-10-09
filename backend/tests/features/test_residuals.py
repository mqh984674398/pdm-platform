"""Condition-normalized residuals for torque vs speed/regime (L4-03)."""

import numpy as np

from .conftest import extraction


def _series(sid, cid, key):
    return [(v.regime_id, v.values[key]) for v in extraction(sid).vectors if v.component_id == cid]


def test_recipe_change_moves_raw_torque_but_not_the_residual():
    # S02 alternates recipes with different speed and load; nothing degrades
    rows = _series("S02", "M01-BS1", "torque_cruise")
    res = [x for _, x in _series("S02", "M01-BS1", "torque_cruise_residual") if x is not None]
    by_regime: dict[str, list[float]] = {}
    for rid, x in rows:
        if rid and x is not None:
            by_regime.setdefault(rid, []).append(x)
    levels = [np.median(v) for v in by_regime.values()]
    assert len(levels) >= 2 and max(levels) / min(levels) > 1.3  # raw torque differs a lot by regime
    assert len(res) >= 0.8 * len(rows)
    assert abs(np.median(res)) < 3 and np.percentile(np.abs(res), 90) < 6


def test_torque_drift_shows_in_the_residual():
    res = [x for _, x in _series("S04", "M01-BS1", "torque_cruise_residual") if x is not None]
    assert len(res) > 30
    assert abs(np.median(res[:10])) < 3
    assert np.median(res[-10:]) > 10


def test_residuals_need_a_known_regime():
    for sid in ("S01", "S17"):
        for v in extraction(sid).vectors:
            residuals = [x for k, x in v.values.items() if k.endswith("residual") and x is not None]
            if v.regime_status != "KNOWN":
                assert residuals == [] and v.regime_id is None
    unsupported = [v for v in extraction("S17").vectors if v.regime_status == "UNSUPPORTED"]
    assert unsupported, "S17 runs in an unknown regime"


def test_actuator_residual_tracks_slowdown():
    # S07 has no speed signal: its regimes come from the operation interval (G2 A2)
    rows = [v for v in extraction("S07").vectors if v.component_id == "M01-CY1"]
    assert all(v.regime_status == "KNOWN" for v in rows)
    ext = [v.values["extend_median"] for v in rows if v.values["extend_median"] is not None]
    res = [v.values["extend_residual"] for v in rows if v.values["extend_residual"] is not None]
    assert np.median(ext[-10:]) > 1.2 * np.median(ext[:10])
    assert len(res) > 0.8 * len(rows) and np.median(res[-10:]) > np.median(res[:10]) + 10
