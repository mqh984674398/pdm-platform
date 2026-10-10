"""T013 AC2: regimes for S02, unsupported regimes for S17, L4-03 normalization (SIMULATED data)."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

import numpy as np

from app.equipment.regimes import assign_regimes, learn_catalog, match
from app.equipment.schemas import OperatingState as S
from app.equipment.schemas import RegimeStatus as R

from .conftest import GOLDEN, _ts, scenario, series


def _by_truth(sid, assignments):
    sc = scenario(sid)
    out = []
    for w in sc.truth:
        mid = _ts(w["window_start"]) + timedelta(seconds=60)
        a = next((a for a in assignments if a.start <= mid <= a.end), None)
        out.append((w, a))
    return out


def test_s02_each_recipe_maps_to_one_known_regime():
    sc = scenario("S02")
    w = sc.window(0, sc.hours)
    cat = learn_catalog(series("S02"), sc.machine, w, "s02")
    assert len(cat.regimes) == 3 and cat.is_simulated
    recipe_to_regime = defaultdict(set)
    for truth, a in _by_truth("S02", assign_regimes(series("S02"), w, cat)):
        if truth["state"] == "RUNNING":
            assert a.status == R.KNOWN, (truth, a)
            recipe_to_regime[truth["recipe_id"]].add(a.regime_id)
        elif a is not None:
            assert a.status == R.NOT_EVALUATED
    assert all(len(v) == 1 for v in recipe_to_regime.values()), recipe_to_regime
    assert len({next(iter(v)) for v in recipe_to_regime.values()}) == 3


def test_s02_regime_change_is_normalized_away():
    """GC-S02-01/02: torque and durations change with the recipe; within the matched regime they stay
    near its reference level, so a recipe change does not look like degradation."""
    sc = scenario("S02")
    w = sc.window(0, sc.hours)
    cat = learn_catalog(series("S02"), sc.machine, w, "s02")
    assignments = assign_regimes(series("S02"), w, cat)
    for fid in ["M01-BS1.torque:cruise", "M01-CY1.extend_time:median", "M01-VC1.release_time:median"]:
        z = np.array(
            [
                f.normalized
                for a in assignments
                for f in a.features
                if f.feature_id == fid and f.normalized is not None
            ]
        )
        assert z.size > 30, fid
        assert np.percentile(np.abs(z), 95) < 3, fid
    levels = {r.regime.regime_id: {x.feature_id: x for x in r.reference} for r in cat.regimes}
    torque = sorted(lv["M01-BS1.torque:cruise"].median for lv in levels.values())
    spread = max(lv["M01-BS1.torque:cruise"].mad for lv in levels.values())
    assert (torque[-1] - torque[0]) > 10 * spread  # raw torque differs strongly between regimes


def test_s17_unknown_regime_is_unsupported():
    sc = scenario("S17")
    cat = learn_catalog(series("S17"), sc.machine, sc.window(0, 96), "s17")
    assignments = assign_regimes(series("S17"), sc.window(0, sc.hours), cat)
    for case in [c for c in GOLDEN if c["scenario_id"] == "S17"]:
        for e in case["expectations"]:
            inside = [
                a
                for a in assignments
                if a.state == S.RUNNING
                and e["start_h"] <= sc.hours_of(a.start)
                and sc.hours_of(a.end) <= e["end_h"]
            ]
            assert inside, (case["case_id"], e)
            want = R.UNSUPPORTED if e["must_abstain"] == "UNSUPPORTED_REGIME" else R.KNOWN
            assert {a.status for a in inside} == {want}, (case["case_id"], e["start_h"])
            if want == R.UNSUPPORTED:
                assert all(
                    a.regime_id is None and all(f.normalized is None for f in a.features) for a in inside
                )


def test_degradation_is_not_turned_into_a_new_regime():
    """S04 torque drift: torque never decides the regime, so drift stays visible as a residual."""
    sc = scenario("S04")
    cat = learn_catalog(series("S04"), sc.machine, sc.window(0, 96), "s04")
    assignments = assign_regimes(series("S04"), sc.window(0, sc.hours), cat)
    running = [a for a in assignments if a.state == S.RUNNING]
    assert running and all(a.status == R.KNOWN for a in running)
    z = [f.normalized for a in running[-10:] for f in a.features if f.feature_id == "M01-BS1.torque:cruise"]
    z = [x for x in z if x is not None]
    assert z and np.median(z) > 3  # late windows sit well above the regime's reference torque


def test_machine_without_speed_uses_operation_intervals():
    # G2 A2: regimes come from cruise speeds and the operation interval; S18 has actuators only
    sc = scenario("S18")
    cat = learn_catalog(series("S18"), sc.machine, sc.window(0, sc.hours), "s18")
    intervals = sorted(round(m.median, 1) for r in cat.regimes for m in r.match_features)
    assert len(cat.regimes) == 2 and all("interval" in r.regime.speed_band for r in cat.regimes)
    assert all(m.feature_id.endswith(":interval") for r in cat.regimes for m in r.match_features)
    assert intervals[0] < intervals[-1]  # the two recipes' cycle periods
    assignments = assign_regimes(series("S18"), sc.window(0, sc.hours), cat)
    running = [a for a in assignments if a.state == S.RUNNING]
    assert running and sum(a.status == R.KNOWN for a in running) > 0.8 * len(running)


def test_regime_needs_speed_or_interval_evidence():
    from app.equipment.regimes import has_regime_evidence

    assert not has_regime_evidence(series("S18"), {"M01-CY1.extend_time:median": 0.3})
    assert not has_regime_evidence(series("S01"), {"M01-CY1.extend_time:interval": 6.0})


def test_sampled_speed_peak_may_fall_short_but_not_exceed():
    sc = scenario("S12")
    cat = learn_catalog(series("S12"), sc.machine, sc.window(0, sc.hours), "s12")
    slow = min(cat.regimes, key=lambda r: r.match_features[0].median)
    fid, c = slow.match_features[0].feature_id, slow.match_features[0].median
    assert match({fid: 0.8 * c}, cat) is slow  # sampling missed the cruise phase
    assert match({fid: 1.2 * c}, cat) is None  # faster than any known regime
