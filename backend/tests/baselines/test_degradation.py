"""Degradation history across maintenance and lifecycle boundaries (L4-05)."""

import numpy as np

from app.monitoring.degradation.history import degradation_history

from ..features.conftest import extraction
from .conftest import sim_events, store, verify


def _history(db, sid, cid, lc, ref, feature, a=96, b=200):
    store(db, sid)
    base = verify(db, sid, cid, lc, ref, a, b)
    return degradation_history(cid, feature, extraction(sid).vectors, {lc: base}, sim_events(sid)), base


def test_drift_rises_in_the_history(db):
    h, _ = _history(db, "S04", "M01-BS1", "M01-BS1-LC1", "ball_screw@1.1.0", "torque_cruise_residual")
    devs = [p.deviation for p in h.segments[0].points]
    assert len(h.segments) == 1 and h.is_simulated
    assert abs(np.median(devs[:10])) < 3 and np.median(devs[-10:]) > 10


def test_lubrication_keeps_the_history_and_shows_its_effect(db):
    h, _ = _history(db, "S09", "M01-BS1", "M01-BS1-LC1", "ball_screw@1.1.0", "torque_cruise_residual")
    assert len(h.segments) == 1  # lubrication does not start a new history
    (step,) = h.steps
    assert step.type == "LUBRICATION" and step.change < -1  # improvement


def test_lubrication_deterioration(db):
    h, _ = _history(db, "S10", "M01-BS1", "M01-BS1-LC1", "ball_screw@1.1.0", "torque_cruise_residual")
    (step,) = h.steps
    assert len(h.segments) == 1 and step.change > 1


def test_partial_repair(db):
    h, _ = _history(db, "S11", "M01-CY1", "M01-CY1-LC1", "pneumatic_cylinder@1.0.0", "extend_median")
    (step,) = h.steps
    assert len(h.segments) == 1 and step.type == "PARTIAL_REPAIR" and step.change < 0
    devs = [p.deviation for p in h.segments[0].points]
    assert all(d is not None for d in devs)


def test_replacement_starts_a_segment_with_its_own_reference(db):
    h, ref1 = _history(db, "S12", "M01-BS1", "M01-BS1-LC1", "ball_screw@1.1.0", "torque_cruise_residual")
    lc1, lc2 = h.segments
    assert (lc1.lifecycle_id, lc2.lifecycle_id) == ("M01-BS1-LC1", "M01-BS1-LC2")
    assert lc1.reference_baseline_id == ref1.baseline_id and lc2.reference_baseline_id is None
    assert all(p.deviation is not None for p in lc1.points)
    assert all(p.deviation is None for p in lc2.points), "LC2 never borrows LC1's reference"
    assert h.steps == []  # a replacement is a boundary, not a step
    assert np.median([p.deviation for p in lc1.points[-10:]]) > 2  # worn before the swap
    ref2 = verify(db, "S12", "M01-BS1", "M01-BS1-LC2", "ball_screw@1.1.0", 520, 650)
    h2 = degradation_history(
        "M01-BS1",
        "torque_cruise_residual",
        extraction("S12").vectors,
        {"M01-BS1-LC1": ref1, "M01-BS1-LC2": ref2},
    )
    assert [p.value for p in h2.segments[0].points] == [p.value for p in lc1.points]  # LC1 history kept
    assert abs(np.median([p.deviation for p in h2.segments[1].points])) < 3


def test_history_through_the_api(client, db):
    from ..lifecycle.conftest import record, seed, sim_maintenance

    seed(client, "S09")
    for m in sim_maintenance("S09"):
        assert record(client, m["component_id"], m["type"], m["performed_at"]).status_code == 201
    store(db, "S09")
    verify(db, "S09", "M01-BS1", "M01-BS1-LC1", "ball_screw@1.1.0", 96, 200)
    r = client.get(
        "/api/components/M01-BS1/degradation",
        params={"feature": "torque_cruise_residual", "feature_ref": "ball_screw@1.1.0"},
    )
    assert r.status_code == 200, r.text
    h = r.json()
    assert len(h["segments"]) == 1 and h["segments"][0]["reference_baseline_id"]
    assert [s["type"] for s in h["steps"]] == ["LUBRICATION"] and h["steps"][0]["change"] < -1
