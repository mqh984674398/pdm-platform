"""Verified healthy reference changes only through an explicit, audited verification (L4-06)."""

from datetime import UTC, datetime

import pytest

from app.core.security import Principal, Role
from app.monitoring.baselines.adaptive import adaptive_baseline
from app.monitoring.baselines.verified import BaselineError, BaselinePermissionError, BaselineService
from app.monitoring.features.store import FeatureStore
from app.monitoring.schemas import BaselineKind, BaselineVerification

from ..features.conftest import extraction
from ..lifecycle.conftest import iso, seed
from .conftest import ENGINEER, store, verify, window

REF = "ball_screw@1.1.0"


def test_verification_is_explicit_and_audited(client, db):
    seed(client, "S01")
    store(db, "S01")
    w = window("S01", 96, 200)
    body = {
        "component_id": "M01-BS1",
        "lifecycle_id": "M01-BS1-LC1",
        "feature_ref": REF,
        "window": {"start": iso(w.start), "end": iso(w.end)},
        "comment": "commissioning acceptance period",
    }
    assert client.post("/api/baselines/verified", body, role="maintenance").status_code == 403
    assert client.post("/api/baselines/verified", {**body, "comment": ""}, role="engineer").status_code == 422
    r = client.post("/api/baselines/verified", body, role="engineer")
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["kind"] == "VERIFIED_HEALTHY" and b["verified_by"] == "u1"
    assert b["meta"]["feature_version"] == REF and b["meta"]["is_simulated"] is True
    assert b["stats"]["torque_cruise_residual"]["n"] >= 5
    audit = client.get("/api/admin/audit", role="admin").json()
    rows = [
        a for a in (audit["items"] if isinstance(audit, dict) else audit) if a["action"] == "baseline.verify"
    ]
    assert len(rows) == 1 and rows[0]["object_id"] == b["baseline_id"]
    assert rows[0]["details"]["comment"] == "commissioning acceptance period"
    listed = client.get("/api/components/M01-BS1/baselines").json()
    assert [x["baseline_id"] for x in listed] == [b["baseline_id"]]


def test_nothing_else_changes_the_reference(db):
    store(db, "S03")
    ref = verify(db, "S03", "M01-BS1", "M01-BS1-LC1", REF, 96, 500)
    svc = BaselineService(db)
    snap = adaptive_baseline(extraction("S03").vectors, "M01-BS1-LC1", datetime.now(UTC))
    snap = snap.model_copy(update={"component_id": "M01-BS1"})
    svc.save_snapshot(snap)
    FeatureStore(db).save(extraction("S03").vectors)  # more data arriving
    db.commit()
    assert svc.verified("M01-BS1", "M01-BS1-LC1", REF) == ref
    with pytest.raises(BaselineError):
        svc.save_snapshot(ref.model_copy(update={"baseline_id": "BL-x"}))


def test_reverification_supersedes_and_keeps_history(db):
    store(db, "S01")
    first = verify(db, "S01", "M01-BS1", "M01-BS1-LC1", REF, 96, 200)
    second = verify(db, "S01", "M01-BS1", "M01-BS1-LC1", REF, 200, 300)
    svc = BaselineService(db)
    assert svc.verified("M01-BS1", "M01-BS1-LC1", REF) == second
    every = svc.baselines("M01-BS1", include_superseded=True)
    assert [b.baseline_id for b in every] == [first.baseline_id, second.baseline_id]
    assert every[0].superseded_by == second.baseline_id


def test_refusals(db):
    store(db, "S01")
    svc = BaselineService(db)
    req = BaselineVerification(
        component_id="M01-BS1",
        lifecycle_id="M01-BS1-LC1",
        feature_ref=REF,
        window=window("S01", 96, 100),
        comment="x",
    )
    with pytest.raises(BaselineError, match="at least"):
        svc.verify(req, ENGINEER)
    with pytest.raises(BaselinePermissionError):
        svc.verify(req, Principal(user_id="m", role=Role.MAINTENANCE))
    other = req.model_copy(update={"lifecycle_id": "M01-BS1-LC9", "window": window("S01", 96, 300)})
    with pytest.raises(BaselineError):
        svc.verify(other, ENGINEER)


def test_healthy_scenario_stays_near_its_reference(db):
    from app.monitoring.baselines.stats import deviation

    store(db, "S01")
    ref = verify(db, "S01", "M01-BS1", "M01-BS1-LC1", REF, 96, 200)
    later = [
        v
        for v in extraction("S01").vectors
        if v.component_id == "M01-BS1" and v.window.start >= ref.window.end
    ]
    devs = [
        deviation(v.values["torque_cruise_residual"], ref.stats["torque_cruise_residual"])
        for v in later
        if v.values["torque_cruise_residual"] is not None
    ]
    assert len(devs) > 10
    assert abs(sorted(devs)[len(devs) // 2]) < 2
    assert ref.kind == BaselineKind.VERIFIED_HEALTHY
