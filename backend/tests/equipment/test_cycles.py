"""T013 AC3: actuator operations segmented; incomplete operations flagged (S18, SIMULATED data)."""

from __future__ import annotations

import numpy as np

from app.equipment.cycles import CycleSignal, motion_segments, operation_cycles
from app.equipment.operations import analyze_machine
from app.equipment.regimes import learn_catalog
from app.equipment.schemas import CycleKind, MotionDirection
from app.equipment.state import observation_windows

from .conftest import GOLDEN, scenario, series

KIND = {
    ("M01-CY1", 0): CycleKind.EXTEND,
    ("M01-CY1", 1): CycleKind.RETRACT,
    ("M01-VC1", 0): CycleKind.VACUUM_RELEASE,
}


def _ops(sid, start_h, end_h, **kw):
    sc = scenario(sid)
    return analyze_machine(sc.machine, series(sid), sc.window(start_h, end_h), sc.lifecycles(), **kw)


def test_s18_incomplete_operations_match_injected_events():
    sc = scenario("S18")
    ops = _ops("S18", 0, sc.hours)
    found = {
        (c.component_id, c.kind, round(c.start.timestamp() - sc.t0.timestamp(), 3))
        for c in ops.cycles
        if not c.complete
    }
    injected = {
        (x["component_id"], KIND[(x["component_id"], x["operation"])], x["t_s"])
        for x in sc.faults["incomplete_operations"]
    }
    assert found == injected and len(found) == 19


def test_s18_timeouts_never_become_durations():
    ops = _ops("S18", 0, scenario("S18").hours)
    bad = [c for c in ops.cycles if not c.complete]
    assert bad and all(c.duration_s is None and c.end is None for c in bad)
    for s in ops.cycle_summaries:
        assert s.timeout_inferred and s.timeout_s == 2.0
        assert s.incomplete_count > 0 and s.completed_count + s.incomplete_count == s.operation_count
        completed = [c.duration_s for c in ops.cycles if c.signal_id == s.signal_id and c.complete]
        assert s.median_duration_s == np.median(completed) and max(completed) < 1.0
        assert s.is_simulated


def test_s18_golden_windows():
    for case in [c for c in GOLDEN if c["scenario_id"] == "S18"]:
        for e in case["expectations"]:
            ops = _ops("S18", e["start_h"], e["end_h"])
            n = sum(s.incomplete_count for s in ops.cycle_summaries if s.component_id == case["component_id"])
            if "WATCH" in e["allowed_health"]:  # incomplete operations present
                assert n > 0, (case["case_id"], e["start_h"])
            else:
                assert n == 0, (case["case_id"], e["start_h"])


def test_clean_scenario_has_no_incomplete_operations():
    ops = _ops("S01", 0, scenario("S01").hours)
    assert ops.cycle_summaries and all(
        s.incomplete_count == 0 and s.timeout_s is None for s in ops.cycle_summaries
    )
    kinds = {s.kind for s in ops.cycle_summaries}
    assert kinds == {CycleKind.EXTEND, CycleKind.RETRACT, CycleKind.VACUUM_RELEASE}


def test_configured_timeout_and_sufficiency():
    sc = scenario("S18")
    s = next(x for x in series("S18") if x.signal.signal_id == "M01-CY1.extend_time")
    cfg = CycleSignal("M01-CY1.extend_time", CycleKind.EXTEND, timeout_s=2.0)
    cycles, summary = operation_cycles(s, "LC", sc.window(0, sc.hours), cfg)
    assert summary.incomplete_count == 4 and not summary.timeout_inferred
    _, few = operation_cycles(s, "LC", sc.window(72, 72.5), cfg)
    assert not few.sufficient and few.min_completed == 10


def test_cycles_carry_lifecycle_and_regime():
    sc = scenario("S01")
    cat = learn_catalog(series("S01"), sc.machine, sc.window(0, sc.hours), "s01")
    ops = _ops("S01", 0, 48, catalog=cat)
    assert ops.catalog_id == "s01"
    assert all(c.lifecycle_id == sc.lifecycles()[c.component_id] for c in ops.cycles)
    assert all(c.regime_id for c in ops.cycles)


def test_motion_segments_alternate_direction():
    s = next(x for x in series("S02") if x.signal.signal_id == "M01-BS1.speed")
    wins = observation_windows(series("S02"))[:3]
    segs = motion_segments(s, "LC", wins)
    assert segs and all(c.kind == CycleKind.MOTION_SEGMENT for c in segs)
    dirs = {c.direction for c in segs}
    assert dirs == {MotionDirection.FORWARD, MotionDirection.REVERSE}
    assert any(c.complete for c in segs)


def test_unit_error_values_are_implausible_not_incomplete():
    """S16: release times delivered in the wrong unit are kept out of statistics but are not timeouts."""
    ops = _ops("S16", 0, scenario("S16").hours)
    s = next(x for x in ops.cycle_summaries if x.signal_id == "M01-VC1.release_time")
    assert s.incomplete_count == 0 and s.timeout_s is None
    assert s.implausible_count > 0 and s.median_duration_s < 1.0
    odd = [c for c in ops.cycles if c.signal_id == s.signal_id and not c.plausible]
    assert len(odd) == s.implausible_count and all(c.complete for c in odd)
