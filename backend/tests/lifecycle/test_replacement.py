"""T014 AC1: replacement (S12) preserves history and starts a new lifecycle (SIMULATED data)."""

from __future__ import annotations

from app.equipment.lifecycle import running_hours
from app.equipment.state import derive_states

from ..equipment.conftest import scenario, series
from .conftest import iso, record, seed, sim_events, sim_maintenance


def test_s12_replacement_matches_simulator_lifecycles(client):
    seed(client, "S12")
    m = sim_maintenance("S12")[0]
    r = record(client, m["component_id"], "REPLACEMENT", m["performed_at"])
    assert r.status_code == 201, r.text
    out = r.json()
    expected_event = sim_events("S12")[0]
    assert out["event"]["lifecycle_id"] == expected_event["lifecycle_id"]
    assert out["event"]["new_lifecycle_id"] == expected_event["new_lifecycle_id"]
    assert out["event"]["is_simulated"] is True

    got = client.get("/api/components/M01-BS1/lifecycles").json()
    want = scenario("S12").topology["lifecycles"]
    keys = ["lifecycle_id", "installed_at", "retired_at", "predecessor_lifecycle_id", "status"]
    norm = lambda x: {k: (x[k].replace("+00:00", "Z") if isinstance(x[k], str) else x[k]) for k in keys}  # noqa: E731
    assert [norm(x) for x in got] == [norm(x) for x in want]


def test_history_is_preserved_across_replacement(client):
    seed(client, "S12")
    sc = scenario("S12")
    t_lub = iso(sc.t0.replace(day=10))
    assert record(client, "M01-BS1", "LUBRICATION", t_lub).status_code == 201
    m = sim_maintenance("S12")[0]
    assert record(client, "M01-BS1", "REPLACEMENT", m["performed_at"]).status_code == 201
    events = client.get("/api/components/M01-BS1/maintenance-events").json()
    assert [(e["type"], e["lifecycle_id"]) for e in events] == [
        ("LUBRICATION", "M01-BS1-LC1"),
        ("REPLACEMENT", "M01-BS1-LC1"),
    ]
    before = client.get("/api/components/M01-BS1/aging", params={"at": t_lub}).json()
    after = client.get("/api/components/M01-BS1/aging", params={"at": iso(sc.t0.replace(day=28))}).json()
    assert before["lifecycle_id"] == "M01-BS1-LC1" and after["lifecycle_id"] == "M01-BS1-LC2"
    assert after["maintenance_since_install"] == 0  # the new installation starts its own count
    # the retired lifecycle stays readable with its own data
    old = client.get("/api/components/M01-BS1/lifecycles").json()[0]
    assert old["status"] == "RETIRED" and old["retired_at"]


def test_usage_accumulates_per_lifecycle(client):
    """Accumulated operation from derived RUNNING time (T013) matches the simulator's per lifecycle."""
    seed(client, "S12")
    sc = scenario("S12")
    m = sim_maintenance("S12")[0]
    record(client, "M01-BS1", "REPLACEMENT", m["performed_at"])
    segments = derive_states(series("S12"), sc.window(0, sc.hours))
    lcs = client.get("/api/components/M01-BS1/lifecycles").json()
    end = sc.window(0, sc.hours).end
    for lc, want in zip(lcs, sc.topology["lifecycles"], strict=True):
        a = sc.t0 if lc["predecessor_lifecycle_id"] is None else sc.window(m["at_h"], m["at_h"] + 1).start
        b = sc.window(m["at_h"], m["at_h"] + 1).start if lc["status"] == "RETIRED" else end
        hours = running_hours(segments, a, b)
        body = {"until": iso(b), "operating_hours": hours, "source": "T013 derived RUNNING time"}
        r = client.post(f"/api/lifecycles/{lc['lifecycle_id']}/usage", body, role="engineer")
        assert r.status_code == 200, r.text
        got = r.json()["accumulated_operating_hours"]
        # derived windows run from first to last sample, the simulator counts whole 2-minute windows
        assert abs(got - want["accumulated_operating_hours"]) / want["accumulated_operating_hours"] < 0.05
        again = client.post(f"/api/lifecycles/{lc['lifecycle_id']}/usage", body, role="engineer")
        assert again.status_code == 409  # a period is counted once


def test_replacement_rules(client):
    seed(client, "S12")
    sc = scenario("S12")
    r = client.post("/api/components/M01-BS1/lifecycles", {"installed_at": iso(sc.t0)}, role="engineer")
    assert r.status_code == 409  # later installations come from replacement events
    assert record(client, "M01-BS1", "REPLACEMENT", iso(sc.t0.replace(year=2025))).status_code == 409
    assert record(client, "M01-BS1", "REPLACEMENT", "2099-01-01T00:00:00Z").status_code == 409  # future
    assert (
        record(client, "M01-BS1", "REPLACEMENT", iso(sc.t0.replace(day=20)), role="viewer").status_code == 403
    )
    assert record(client, "NOPE", "REPLACEMENT", iso(sc.t0.replace(day=20))).status_code == 404
    assert record(client, "M01-BS1", "REPLACEMENT", iso(sc.t0.replace(day=20))).status_code == 201
    assert (
        record(client, "M01-BS1", "LUBRICATION", iso(sc.t0.replace(day=15))).status_code == 409
    )  # out of order
