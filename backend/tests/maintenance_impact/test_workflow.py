"""T018 AC2: the analysis drives the post-maintenance workflow along the Golden Case path."""

from datetime import timedelta

import pytest

from app.equipment.maintenance_impact.service import ImpactService

from ..lifecycle.conftest import record, seed, sim_maintenance
from .conftest import GOLDEN, catalog, scenario, series

CASES = [
    pytest.param(c, e, id=c["case_id"])
    for c in GOLDEN
    if c["scenario_id"] in {"S09", "S10", "S11", "S12"}
    for e in c["expectations"]
    if e["workflow"]
]


@pytest.mark.parametrize(("case", "exp"), CASES)
def test_workflow_follows_golden_path(case, exp, client, db):
    sid, cid = case["scenario_id"], case["component_id"]
    sc = scenario(sid)
    seed(client, sid)
    (m,) = sim_maintenance(sid)
    assert record(client, cid, m["type"], m["performed_at"]).status_code == 201
    (wf,) = client.get("/api/maintenance-workflows", params={"component_id": cid}).json()
    svc = ImpactService(db)
    at = sc.t0 + timedelta(hours=m["at_h"])
    # the next golden span says by when the workflow must have finished
    nxt = min(e["start_h"] for e in case["expectations"] if e["start_h"] > exp["start_h"])
    final = None
    for h in range(1, int(nxt - m["at_h"]) + 1):
        out = svc.advance(wf["workflow_id"], series(sid), catalog(sid), now=at + timedelta(hours=h))
        db.commit()
        if out.state.value in ("NORMAL_MONITORING", "REVIEW_REQUIRED"):
            final = out
            break
    assert final is not None, f"workflow still open at {nxt} h"
    assert [t.to_state.value for t in final.transitions] == exp["workflow"]
    assert all(t.by == "system:maintenance-impact" for t in final.transitions[1:])
    impact = svc.impact(wf["workflow_id"])
    assert impact is not None and impact.is_simulated
    audit = client.get("/api/admin/audit", role="admin").json()
    rows = audit["items"] if isinstance(audit, dict) else audit
    assert any(a["action"] == "maintenance_impact.analyze" for a in rows)


def test_review_is_still_a_human_step(client, db):
    sid = "S10"
    sc = scenario(sid)
    seed(client, sid)
    (m,) = sim_maintenance(sid)
    record(client, "M01-BS1", m["type"], m["performed_at"])
    (wf,) = client.get("/api/maintenance-workflows", params={"component_id": "M01-BS1"}).json()
    svc = ImpactService(db)
    at = sc.t0 + timedelta(hours=m["at_h"])
    out = svc.advance(wf["workflow_id"], series(sid), catalog(sid), now=at + timedelta(hours=45))
    db.commit()
    assert out.state.value == "REVIEW_REQUIRED"
    again = svc.advance(wf["workflow_id"], series(sid), catalog(sid), now=at + timedelta(hours=200))
    assert again.state.value == "REVIEW_REQUIRED"  # the system never closes a review


def test_waiting_for_data_then_review(client, db):
    from app.equipment.schemas import ImpactConfig

    sid = "S09"
    sc = scenario(sid)
    seed(client, sid)
    (m,) = sim_maintenance(sid)
    record(client, "M01-BS1", m["type"], m["performed_at"])
    (wf,) = client.get("/api/maintenance-workflows", params={"component_id": "M01-BS1"}).json()
    svc = ImpactService(db)
    at = sc.t0 + timedelta(hours=m["at_h"])
    cfg = ImpactConfig(validation_hours=1, max_validation_hours=2, min_post_windows=50)
    mid = svc.advance(wf["workflow_id"], series(sid), catalog(sid), now=at + timedelta(hours=5.5), config=cfg)
    db.commit()
    assert mid.state.value == "POST_MAINTENANCE_VALIDATION"
    assert svc.impact(wf["workflow_id"]).outcome.value == "UNKNOWN"
    end = svc.advance(wf["workflow_id"], series(sid), catalog(sid), now=at + timedelta(hours=7), config=cfg)
    assert end.state.value == "REVIEW_REQUIRED"
