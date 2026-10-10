"""T014 AC3: workflow transitions are enforced and audited (SIMULATED topology)."""

from __future__ import annotations

from ..equipment.conftest import scenario
from .conftest import iso, record, seed

T = "/api/maintenance-workflows/{}/transitions"


def _start(client, day=10, type_="LUBRICATION"):
    seed(client, "S09")
    r = record(client, "M01-BS1", type_, iso(scenario("S09").t0.replace(day=day)))
    assert r.status_code == 201, r.text
    return r.json()["workflow"]


def _move(client, wid, target, role="maintenance", comment="", expected=None):
    body = {"target": target, "comment": comment, "expected_state": expected}
    return client.post(T.format(wid), body, role=role)


def test_full_path_to_normal_monitoring_is_audited(client):
    wf = _start(client)
    assert wf["state"] == "MAINTENANCE_EVENT" and wf["lifecycle_id"] == "M01-BS1-LC1" and wf["is_simulated"]
    for target in ["STABILIZATION", "POST_MAINTENANCE_VALIDATION", "NORMAL_MONITORING"]:
        r = _move(client, wf["workflow_id"], target)
        assert r.status_code == 200, r.text
    got = client.get(f"/api/maintenance-workflows/{wf['workflow_id']}").json()
    assert [(t["from_state"], t["to_state"]) for t in got["transitions"]] == [
        (None, "MAINTENANCE_EVENT"),
        ("MAINTENANCE_EVENT", "STABILIZATION"),
        ("STABILIZATION", "POST_MAINTENANCE_VALIDATION"),
        ("POST_MAINTENANCE_VALIDATION", "NORMAL_MONITORING"),
    ]
    audit = client.get(
        "/api/admin/audit", role="admin", params={"object_type": "maintenance_workflow"}
    ).json()
    actions = [
        (a["action"], a["details"].get("to_state")) for a in audit if a["object_id"] == wf["workflow_id"]
    ]
    assert actions == [
        ("maintenance_workflow.start", "MAINTENANCE_EVENT"),
        ("maintenance_workflow.transition", "STABILIZATION"),
        ("maintenance_workflow.transition", "POST_MAINTENANCE_VALIDATION"),
        ("maintenance_workflow.transition", "NORMAL_MONITORING"),
    ]
    assert all(a["actor"] == "u1" for a in audit)
    events = client.get("/api/admin/audit", role="admin", params={"object_type": "maintenance_event"}).json()
    assert [e["action"] for e in events] == ["maintenance.event"]


def test_illegal_transitions_are_refused_and_not_recorded(client):
    wf = _start(client)
    wid = wf["workflow_id"]
    for target in [
        "POST_MAINTENANCE_VALIDATION",
        "NORMAL_MONITORING",
        "REVIEW_REQUIRED",
        "MAINTENANCE_EVENT",
    ]:
        r = _move(client, wid, target)
        assert r.status_code == 409, target
        assert r.json()["code"] == "workflow_transition_refused"
    assert _move(client, wid, "STABILIZATION", expected="POST_MAINTENANCE_VALIDATION").status_code == 409
    assert _move(client, wid, "STABILIZATION", role="viewer").status_code == 403
    got = client.get(f"/api/maintenance-workflows/{wid}").json()
    assert got["state"] == "MAINTENANCE_EVENT" and len(got["transitions"]) == 1
    audit = client.get("/api/admin/audit", role="admin", params={"object_id": wid}).json()
    assert [a["action"] for a in audit] == ["maintenance_workflow.start"]


def test_review_required_needs_engineer_and_comment(client):
    wid = _start(client)["workflow_id"]
    for target in ["STABILIZATION", "POST_MAINTENANCE_VALIDATION", "REVIEW_REQUIRED"]:
        assert _move(client, wid, target).status_code == 200
    assert _move(client, wid, "NORMAL_MONITORING", comment="looks fine").status_code == 403
    assert _move(client, wid, "NORMAL_MONITORING", role="engineer").status_code == 409  # no comment
    r = _move(
        client, wid, "NORMAL_MONITORING", role="engineer", comment="torque back in band after re-greasing"
    )
    assert r.status_code == 200 and r.json()["state"] == "NORMAL_MONITORING"
    assert r.json()["transitions"][-1]["comment"].startswith("torque back")


def test_new_event_supersedes_open_workflow(client):
    first = _start(client, day=10)
    assert _move(client, first["workflow_id"], "STABILIZATION").status_code == 200
    r = record(client, "M01-BS1", "ADJUSTMENT", iso(scenario("S09").t0.replace(day=12)))
    second = r.json()
    assert second["superseded"] == [first["workflow_id"]]
    old = client.get(f"/api/maintenance-workflows/{first['workflow_id']}").json()
    assert old["superseded_by"] == second["workflow"]["workflow_id"] and old["state"] == "STABILIZATION"
    assert _move(client, first["workflow_id"], "POST_MAINTENANCE_VALIDATION").status_code == 409
    open_ = client.get("/api/maintenance-workflows", params={"component_id": "M01-BS1", "open": True}).json()
    assert [w["workflow_id"] for w in open_] == [second["workflow"]["workflow_id"]]


def test_inspection_starts_no_workflow(client):
    seed(client, "S09")
    r = record(client, "M01-BS1", "INSPECTION", iso(scenario("S09").t0.replace(day=5)))
    assert r.status_code == 201 and r.json()["workflow"] is None


def test_replacement_workflow_monitors_the_new_lifecycle(client):
    wf = _start(client, day=20, type_="REPLACEMENT")
    assert wf["lifecycle_id"] == "M01-BS1-LC2"
