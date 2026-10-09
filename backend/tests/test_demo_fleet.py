"""T007: the demo fleet fixture is reproducible, labeled simulated, and consistent with Golden Cases."""

import json

from app.decision.schemas import HealthState
from app.simulation.demo_fleet import FLEET, build_fleet
from app.simulation.golden import DATA_DIR, load_golden_cases

FIXTURE = DATA_DIR / "fixtures" / "demo_fleet.json"


def fleet() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_matches_generator():
    assert fleet() == json.loads(json.dumps(build_fleet(DATA_DIR)))


def test_labeled_simulated_with_basis_in_both_languages():
    f = fleet()
    assert f["is_simulated"] is True
    assert "Golden Case" in f["health_basis"]["en"] and f["health_basis"]["zh"]
    assert [m["machine_id"] for m in f["machines"]] == [x[0] for x in FLEET]


def test_every_health_state_is_demonstrated():
    states = {c["health"] for m in fleet()["machines"] for c in m["components"]}
    assert states == {s.value for s in HealthState}


def test_component_ids_unique_and_prefixed_by_machine():
    ids = [(m["machine_id"], c["component_id"]) for m in fleet()["machines"] for c in m["components"]]
    assert len({c for _, c in ids}) == len(ids)
    assert all(c.startswith(f"{m}-") for m, c in ids)


def test_health_is_allowed_by_golden_case_at_snapshot():
    cases = load_golden_cases()
    days = {m: d for m, _, d, _, _ in FLEET}
    checked = 0
    for m in fleet()["machines"]:
        for c in m["components"]:
            case = next(
                (
                    g
                    for g in cases
                    if g.scenario_id == m["scenario_id"] and g.component_id == c["source_component_id"]
                ),
                None,
            )
            if case is None:
                continue
            hour = days[m["machine_id"]] * 24
            exp = [e for e in case.expectations if e.start_h <= hour < e.end_h]
            if exp:
                assert HealthState(c["health"]) in exp[0].allowed_health, c["component_id"]
                checked += 1
    assert checked >= 5


def test_trend_is_history_only_and_single_regime():
    for m in fleet()["machines"]:
        snap = m["snapshot_at"]
        for c in m["components"]:
            for tr in c["trend"]:
                assert c["trend_regime"] == "R-A"
                assert all(ts <= snap for ts, _ in tr["points"]), c["component_id"]


def test_template_components_have_no_telemetry_and_unknown_health():
    templates = [c for m in fleet()["machines"] for c in m["components"] if c["source_component_id"] is None]
    assert templates and all(c["health"] == "UNKNOWN" and not c["signals"] for c in templates)
