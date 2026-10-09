"""No future data: vectors depend only on rows up to their window end (L4-04 leakage test)."""

from dataclasses import replace
from datetime import timedelta

import numpy as np
import pytest

from app.equipment.regimes import learn_catalog
from app.monitoring.features.extract import extract_features

from ..equipment.conftest import scenario, series
from .conftest import catalog, components, lifecycles


def _run(sid, ser, end_h, as_of=None):
    sc = scenario(sid)
    return extract_features(
        ser,
        sc.window(96, end_h),
        components(sid),
        lifecycles(sid),
        catalog(sid),
        sc.maintenance(),
        as_of=as_of,
    )


@pytest.mark.parametrize("sid", ["S04", "S06"])
def test_future_rows_never_change_a_vector(sid):
    sc = scenario(sid)
    cut = sc.t0 + timedelta(hours=200)
    full = _run(sid, series(sid), sc.hours, as_of=cut)
    # the same period, with every row after the cut replaced by absurd values
    poisoned = []
    for s in series(sid):
        v = s.v.copy()
        v[s.t > cut.timestamp()] = 1e6
        poisoned.append(replace(s, v=v))
    p = _run(sid, poisoned, sc.hours, as_of=cut)
    # and with only the rows up to the cut loaded
    trimmed = [replace(s, t=s.t[s.t <= cut.timestamp()], v=s.v[s.t <= cut.timestamp()]) for s in series(sid)]
    t = _run(sid, trimmed, 200)
    assert full.vectors and full.vectors == p.vectors == t.vectors
    assert all(v.window.end <= cut for v in full.vectors)


def test_later_extraction_keeps_earlier_vectors():
    early = _run("S04", series("S04"), 200)
    late = _run("S04", series("S04"), scenario("S04").hours)
    keyed = {(v.component_id, v.window.start): v for v in late.vectors}
    assert early.vectors and all(keyed[(v.component_id, v.window.start)] == v for v in early.vectors)


def test_open_window_at_as_of_is_not_emitted():
    sc = scenario("S01")
    ser = series("S01")
    full = _run("S01", ser, sc.hours)
    mid = next(v for v in full.vectors if v.window.start > sc.t0 + timedelta(hours=150))
    as_of = mid.window.start + (mid.window.end - mid.window.start) / 2
    r = _run("S01", ser, sc.hours, as_of=as_of)
    assert all(v.window.end < as_of for v in r.vectors)
    assert not any(v.window.start == mid.window.start for v in r.vectors)


def test_catalog_learned_inside_the_window_is_refused():
    sc = scenario("S01")
    cat = learn_catalog(series("S01"), sc.machine, sc.window(0, 150), "overlap")
    with pytest.raises(ValueError, match="before the extraction window"):
        extract_features(series("S01"), sc.window(96, 200), components("S01"), lifecycles("S01"), cat)


def test_values_come_from_the_window_rows_only():
    r = _run("S06", series("S06"), 150)
    s = next(x for x in series("S06") if x.signal.signal_id == "M01-VC1.release_time")
    for v in [v for v in r.vectors if v.component_id == "M01-VC1"][:5]:
        _, vals = s.between(v.window.start.timestamp(), v.window.end.timestamp())
        assert v.values["operation_count"] == np.count_nonzero(~np.isnan(vals))
