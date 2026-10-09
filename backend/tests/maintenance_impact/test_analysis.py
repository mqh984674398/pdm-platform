"""T018 AC1–AC3 on the impact analysis (SIMULATED data)."""

from datetime import timedelta

import pytest

from app.equipment.maintenance_impact.analysis import analyze_impact
from app.equipment.schemas import ImpactConfig
from app.equipment.schemas import ImpactOutcome as O

from .conftest import catalog, scenario, series


def _impact(sid, cid=None, at_h=None, **cfg):
    sc = scenario(sid)
    m = sc.cfg["maintenance"][0] if sc.cfg.get("maintenance") else None
    cid = cid or m["component_id"]
    at = sc.t0 + timedelta(hours=at_h if at_h is not None else m["at_h"])
    return analyze_impact(series(sid), cid, at, catalog(sid), ImpactConfig(**cfg))


def test_lubrication_improves():
    r = _impact("S09")
    (f,) = r.features
    assert r.outcome == O.IMPROVED and f.feature_id == "M01-BS1.torque:cruise"
    assert f.change < -2 and abs(f.post_level) < 3 and r.is_simulated


def test_lubrication_deteriorates():
    r = _impact("S10")
    assert r.outcome == O.DETERIORATED and r.features[0].change > 2


def test_partial_repair_is_reported_as_partial():
    r = _impact("S11")
    ext = next(f for f in r.features if f.feature_id == "M01-CY1.extend_time:median")
    assert r.outcome == O.PARTIAL and ext.outcome == O.PARTIAL
    assert ext.change < -2 and ext.post_level >= 3  # better than before, still well above the reference


def test_only_compatible_regimes_are_compared():
    r = _impact("S09")
    for f in r.features:
        assert f.regimes
        for c in f.regimes:
            assert c.pre_windows >= 3 and c.post_windows >= 1
    # speeds and intervals define regimes; they are never reported as maintenance effects
    assert all(
        f.feature_id.endswith((":cruise", ":median")) and "speed" not in f.feature_id for f in r.features
    )


def test_recipe_change_is_not_a_maintenance_effect():
    # S02 switches recipes; nothing is maintained. A fake event must show no change
    sc = scenario("S02")
    for h in (150, 200, 250):
        r = _impact("S02", "M01-BS1", h)
        assert r.outcome in (O.NO_CHANGE, O.UNKNOWN), (h, r.features)
    assert sc.hours > 250


def test_insufficient_data_is_unknown():
    r = _impact("S09", validation_hours=1)
    assert r.outcome == O.UNKNOWN and all(f.outcome == O.UNKNOWN for f in r.features)
    assert r.reason.en.startswith("Not enough")


def test_stabilization_window_is_configurable():
    short, long_ = _impact("S09", stabilization_hours=0), _impact("S09", stabilization_hours=30)
    sc = scenario("S09")
    assert short.post.start == sc.t0 + timedelta(hours=360)
    assert long_.post.start == sc.t0 + timedelta(hours=390)
    with pytest.raises(ValueError):
        ImpactConfig(stabilization_hours=-1)


def test_catalog_after_the_event_is_refused():
    sc = scenario("S09")
    with pytest.raises(ValueError, match="before the maintenance event"):
        analyze_impact(series("S09"), "M01-BS1", sc.t0 + timedelta(hours=50), catalog("S09"))
