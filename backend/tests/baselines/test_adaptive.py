"""Adaptive baseline follows regime-normalized behavior; aging shows against the frozen reference."""

import numpy as np

from app.monitoring.baselines.adaptive import adaptive_track
from app.monitoring.baselines.stats import deviation

from ..features.conftest import extraction
from .conftest import store, verify

F = "torque_cruise_residual"


def test_normal_aging_visible_against_the_frozen_reference(db):
    store(db, "S03")
    ref = verify(db, "S03", "M01-BS1", "M01-BS1-LC1", "ball_screw@1.1.0", 96, 500)
    vs = [v for v in extraction("S03").vectors if v.component_id == "M01-BS1"]
    track = adaptive_track(vs, F)
    stats = ref.stats[F]
    early = [deviation(p.mean, stats) for p in track[:20]]
    late = [deviation(p.mean, stats) for p in track[-20:]]
    assert abs(np.median(early)) < 2
    assert np.median(late) > 3, "aging moves the adaptive baseline away from the verified reference"
    # the adaptive baseline itself follows the data: recent values sit close to it
    recent = [v.values[F] for v in vs if v.values[F] is not None][-20:]
    gap = abs(np.median(recent) - track[-1].mean)
    assert gap < 0.25 * abs(track[-1].mean - stats.mean)


def test_actuator_aging_too(db):
    store(db, "S03")
    ref = verify(db, "S03", "M01-CY1", "M01-CY1-LC1", "pneumatic_cylinder@1.0.0", 96, 500)
    vs = [v for v in extraction("S03").vectors if v.component_id == "M01-CY1"]
    track = adaptive_track(vs, "extend_median")
    assert deviation(track[-1].mean, ref.stats["extend_median"]) > 3


def test_track_restarts_with_each_lifecycle():
    vs = [v for v in extraction("S12").vectors if v.component_id == "M01-BS1"]
    track = adaptive_track(vs, "torque_cruise")
    lcs = [p.lifecycle_id for p in track]
    first_lc2 = lcs.index("M01-BS1-LC2")
    assert track[first_lc2].n == 1
    assert lcs[:first_lc2] == ["M01-BS1-LC1"] * first_lc2
