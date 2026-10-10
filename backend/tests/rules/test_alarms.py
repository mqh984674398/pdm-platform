"""T017 AC3: alarm lifecycle (raised, acknowledged, resolved) with audit."""

from ..lifecycle.conftest import seed
from .conftest import REF, references, store

BODY = {"component_id": "M01-BS1", "feature_ref": "ball_screw@1.1.0"}


def _audit(client):
    audit = client.get("/api/admin/audit", role="admin").json()
    return [
        a for a in (audit["items"] if isinstance(audit, dict) else audit) if a["action"].startswith("alarm.")
    ]


def test_drift_raises_escalates_and_is_handled(client, db):
    seed(client, "S04")
    references(db, "S04")
    db.commit()
    assert client.post("/api/alarms/evaluate", BODY, role="maintenance").status_code == 403
    r = client.post("/api/alarms/evaluate", BODY, role="engineer")
    assert r.status_code == 200, r.text
    assert len(r.json()["raised"]) == 1 and r.json()["is_simulated"]
    (alarm,) = client.get("/api/alarms", params={"component_id": "M01-BS1"}).json()
    assert alarm["rule_id"] == "ST-TORQUE" and alarm["status"] == "RAISED" and alarm["severity"] == "CRITICAL"
    assert alarm["rules_version"] == "pdm-rules@1.0.0+0" and alarm["is_simulated"] and alarm["evidence_ids"]
    actions = [a["action"] for a in _audit(client)]
    assert actions[0] == "alarm.raise" and "alarm.escalate" in actions
    # evaluating again is idempotent
    again = client.post("/api/alarms/evaluate", BODY, role="engineer").json()
    assert again["raised"] == [] and again["updated"] == []
    aid = alarm["alarm_id"]
    assert client.post(f"/api/alarms/{aid}/acknowledge", {}, role="viewer").status_code == 403
    ack = client.post(f"/api/alarms/{aid}/acknowledge", {"comment": "seen"}, role="maintenance")
    assert (
        ack.status_code == 200
        and ack.json()["status"] == "ACKNOWLEDGED"
        and ack.json()["acknowledged_by"] == "u1"
    )
    assert client.post(f"/api/alarms/{aid}/acknowledge", {}, role="maintenance").status_code == 409
    assert client.post(f"/api/alarms/{aid}/resolve", {"comment": " "}, role="maintenance").status_code == 409
    res = client.post(f"/api/alarms/{aid}/resolve", {"comment": "lubricated; monitoring"}, role="maintenance")
    assert res.status_code == 200 and res.json()["status"] == "RESOLVED"
    assert (
        client.post(f"/api/alarms/{aid}/resolve", {"comment": "again"}, role="maintenance").status_code == 409
    )
    assert [a["action"] for a in _audit(client)][-2:] == ["alarm.acknowledge", "alarm.resolve"]
    assert client.get("/api/alarms", params={"status": "RESOLVED"}).json()[0]["resolution_comment"] == (
        "lubricated; monitoring"
    )
    assert client.post("/api/alarms/AL-missing/acknowledge", {}, role="maintenance").status_code == 404


def test_condition_cleared_and_new_alarm_after_resolution(db):
    from app.monitoring.alarms.service import AlarmService
    from app.monitoring.rules.definitions import DEFAULT_RULES
    from app.monitoring.rules.engine import evaluate

    from ..baselines.conftest import ENGINEER
    from .conftest import after_reference

    ref = references(db, "S04")["M01-BS1"]
    evals = evaluate(after_reference("S04", "M01-BS1"), {ref.lifecycle_id: ref}, DEFAULT_RULES)
    first = [e for e in evals if e.hits][:5]
    quiet = [e for e in evals if not e.hits and "ST-TORQUE" not in e.not_evaluated]
    svc = AlarmService(db)
    (aid,), _ = svc.sync(first, ENGINEER)
    # a later window where the rule no longer fires (synthetic order: quiet windows re-dated after)
    cleared = quiet[0].model_copy(update={"window": evals[-1].window})
    _, updated = svc.sync([cleared], ENGINEER)
    assert updated == [aid] and svc.alarms()[0].condition_active is False
    svc.resolve(aid, ENGINEER, "checked")
    assert REF == (96.0, 168.0)
    w = evals[-1].window
    later = first[-1].model_copy(
        update={"window": w.model_copy(update={"start": w.end, "end": w.end + (w.end - w.start)})}
    )
    raised, _ = svc.sync([later], ENGINEER)
    assert len(raised) == 1 and raised[0] != aid


__all__ = ["store"]
