"""T013 AC1: operating state from evidence, UNKNOWN when evidence is insufficient (SIMULATED data)."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

import numpy as np
import pytest

from app.core.schemas import LocalizedText
from app.equipment.operations import analyze_machine
from app.equipment.schemas import OperatingState as S
from app.equipment.state import Series, derive_states, moving, state_at
from app.signals.schemas import PhysicalQuantity, SignalDefinition

from .conftest import _ts, scenario, series


def _truth_vs_derived(sid: str, maintenance=()) -> Counter:
    sc = scenario(sid)
    segs = derive_states(series(sid), sc.window(0, sc.hours), maintenance)
    out: Counter = Counter()
    for w in sc.truth:
        mid = _ts(w["window_start"]) + timedelta(seconds=60)
        out[(w["state"], state_at(segs, mid).value)] += 1
    return out


@pytest.mark.parametrize("sid", ["S01", "S02", "S12", "S17"])
def test_states_match_truth_where_evidence_exists(sid):
    c = _truth_vs_derived(sid)
    # RUNNING and IDLE are evidenced by the speed signals; a stopped machine sends nothing -> UNKNOWN
    allowed = {("RUNNING", "RUNNING"), ("IDLE", "IDLE"), ("STOPPED", "UNKNOWN")}
    assert set(c) <= allowed, c
    assert c[("RUNNING", "RUNNING")] > 0


def test_actuator_only_machine_needs_operations_as_evidence():
    c = _truth_vs_derived("S18")  # cylinder and vacuum cup only: no speed signal
    assert set(c) <= {("RUNNING", "RUNNING"), ("IDLE", "UNKNOWN"), ("STOPPED", "UNKNOWN")}, c
    assert c[("IDLE", "UNKNOWN")] > 0


def test_segments_cover_the_window_and_gaps_are_unknown():
    sc = scenario("S01")
    w = sc.window(0, 48)
    segs = derive_states(series("S01"), w)
    assert segs[0].start == w.start and segs[-1].end == w.end
    assert all(a.end <= b.start for a, b in zip(segs, segs[1:], strict=False))
    gaps = [s for s in segs if s.state == S.UNKNOWN]
    assert gaps and all(s.reason.en.startswith("No data") and not s.evidence for s in gaps)
    assert all(s.is_simulated for s in segs)
    running = [s for s in segs if s.state == S.RUNNING]
    assert all("M01-BS1.speed" in s.evidence for s in running)


def test_maintenance_record_overrides_telemetry():
    sc = scenario("S12")
    rec = sc.maintenance()
    assert rec, "S12 has a replacement"
    a, b, rid = rec[0]
    segs = derive_states(series("S12"), sc.window(480, 528), rec)
    maint = [s for s in segs if s.state == S.MAINTENANCE]
    assert len(maint) == 1 and maint[0].start == a and maint[0].end == b and maint[0].evidence == [rid]


def test_stopped_and_fault_are_never_guessed():
    sc = scenario("S02")
    ops = analyze_machine(sc.machine, series("S02"), sc.window(0, sc.hours), sc.lifecycles())
    assert {s.state for s in ops.states} <= {S.RUNNING, S.IDLE, S.UNKNOWN}
    assert set(ops.not_evaluated) == {S.STOPPED, S.FAULT}


def _series(v, quantity=PhysicalQuantity.SPEED, expected=2.0) -> Series:
    sig = SignalDefinition(
        signal_id="X.speed",
        name=LocalizedText(zh="x", en="x"),
        quantity=quantity,
        unit="rpm",
        expected_sampling_s=expected,
    )
    t = 1_700_000_000 + np.arange(len(v)) * 2.0
    return Series(sig, "X", t, np.asarray(v, float), True)


def test_motion_detection_handles_constant_rotation_and_noise():
    rng = np.random.default_rng(1)
    assert moving(1000 + rng.normal(0, 2, 60)) is True  # continuous rotation, no standstill samples
    assert moving(rng.normal(0, 0.5, 60)) is False  # servo holding position
    assert moving(np.array([np.nan] * 10)) is None


def test_only_missing_values_is_unknown():
    s = _series([np.nan] * 30)
    w = scenario("S01").window(0, 1)
    s.t = w.start.timestamp() + 60 + np.arange(30) * 2.0
    segs = derive_states([s], w)
    assert [x.state for x in segs] == [S.UNKNOWN, S.UNKNOWN, S.UNKNOWN]
    assert segs[1].reason.en.startswith("Only missing values")
