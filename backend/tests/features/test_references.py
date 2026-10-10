"""Vectors carry regime, lifecycle and source window references (L4-04, GEN-06)."""

from datetime import timedelta

from app.monitoring.features.extract import extract_features

from ..equipment.conftest import scenario, series
from .conftest import REFERENCE_H, catalog, components, extraction, lifecycles


def test_every_vector_is_traceable():
    for sid in ("S01", "S02", "S17"):
        sc = scenario(sid)
        signals = {c["component_id"]: set(c["signal_ids"]) for c in sc.topology["components"]}
        for v in extraction(sid).vectors:
            assert v.window.start >= sc.t0 + timedelta(hours=REFERENCE_H)
            assert v.window.start < v.window.end
            assert v.lifecycle_id.startswith(v.component_id)
            assert v.source_signals and set(v.source_signals) <= signals[v.component_id]
            assert v.catalog_id == f"{sid}-ref"
            assert (v.regime_id is not None) == (v.regime_status == "KNOWN")


def test_replacement_switches_lifecycle():
    vs = [v for v in extraction("S12").vectors if v.component_id == "M01-BS1"]
    swap = scenario("S12").t0 + timedelta(hours=504)
    assert {v.lifecycle_id for v in vs if v.window.end <= swap} == {"M01-BS1-LC1"}
    assert {v.lifecycle_id for v in vs if v.window.start >= swap} == {"M01-BS1-LC2"}


def test_window_spanning_a_replacement_is_skipped():
    sid = "S01"
    sc = scenario(sid)
    base = extraction(sid)
    w = next(v for v in base.vectors if v.component_id == "M01-BS1").window
    change = w.start + (w.end - w.start) / 2
    lcs = dict(lifecycles(sid))
    lcs["M01-BS1"] = [("M01-BS1-LC1", sc.t0, change), ("M01-BS1-LC2", change, None)]
    r = extract_features(
        series(sid), sc.window(REFERENCE_H, sc.hours), components(sid), lcs, catalog(sid), sc.maintenance()
    )
    assert not any(v.component_id == "M01-BS1" and v.window == w for v in r.vectors)
    skip = [s for s in r.skipped if s.component_id == "M01-BS1" and s.window == w]
    assert skip and skip[0].reason.en == "Window spans a component replacement"


def test_maintenance_windows_get_no_vectors():
    sid = "S09"
    sc = scenario(sid)
    maint = sc.maintenance()
    assert maint
    r = extraction(sid)
    for a, b, _ in maint:
        assert not any(v.window.start <= b and v.window.end >= a for v in r.vectors)
