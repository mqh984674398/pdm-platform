"""T020: simulated adapter -> features -> rules -> alarms -> dashboard API, end to end (SIMULATED).

Four demo machines are replayed through the pipeline into a fresh application database (PostgreSQL
when PDM_TEST_PG_URL is set); the dashboard endpoints are then read as a viewer.
"""

from datetime import timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.core.audit  # noqa: F401  (registers tables)
import app.datasource.query_service.registry  # noqa: F401
import app.equipment.lifecycle  # noqa: F401
import app.equipment.maintenance  # noqa: F401
import app.equipment.maintenance_impact.service  # noqa: F401
import app.monitoring.alarms.service  # noqa: F401
import app.monitoring.baselines.verified  # noqa: F401
import app.monitoring.features.store  # noqa: F401
import app.monitoring.rules.settings  # noqa: F401
import app.signals.registry  # noqa: F401
from app.core.audit import AuditRecord
from app.core.db import Base, get_session
from app.datasource.query_service.sources import DataSourceRegistry
from app.decision.fleet import FleetHealthService
from app.main import create_app
from app.simulation.demo_pipeline import DEMO_FLEET, add_demo_source, demo_machines, run_pipeline

from ..datasource.conftest import PG_URL
from ..equipment.conftest import DATA
from ..query_service.conftest import Client

SELECTED = ["A02", "A05", "A07", "A10"]  # S04 drift, S12 replacement, S20 interruption, S10 lubrication


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    engine = create_engine(PG_URL or f"sqlite:///{tmp_path_factory.mktemp('fleet') / 'app.db'}")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    machines = demo_machines(DATA, [r for r in DEMO_FLEET if r[0] in SELECTED])
    sources = DataSourceRegistry()
    add_demo_source(sources, machines)
    with factory() as s:
        results = {r.machine_id: r for r in run_pipeline(s, sources, machines)}

    def session():
        with factory() as s:
            yield s

    application = create_app(sources=sources)
    application.dependency_overrides[get_session] = session
    yield Client(application), factory, results
    engine.dispose()


def _fleet(client):
    r = client.get("/api/fleet")
    assert r.status_code == 200, r.text
    return r.json()


def _component(fleet, cid):
    return next(c for m in fleet["machines"] for c in m["components"] if c["component_id"] == cid)


def test_overview_is_computed_from_the_pipeline_and_marked_simulated(env):
    client, _, results = env
    fleet = _fleet(client)
    assert fleet["is_simulated"] and fleet["rules_version"].startswith("pdm-rules@1.0.0")
    assert [m["machine_id"] for m in fleet["machines"]] == SELECTED
    assert all(c["is_simulated"] for m in fleet["machines"] for c in m["components"])
    assert all(r.vectors > 0 and r.references for r in results.values())
    bs1 = _component(fleet, "A02-BS1")
    assert bs1["health"] == "CRITICAL" and "ST-TORQUE" in bs1["reason"]["en"]
    assert bs1["open_alarms"] == 1 and bs1["trend"][0]["rule_id"] == "ST-TORQUE"
    assert bs1["trend"][0]["points"] and bs1["signals"]
    assert _component(fleet, "A02-LM1")["health"] == "NORMAL"


def test_replacement_is_judged_against_the_new_lifecycles_reference(env):
    client, _, _ = env
    bs1 = _component(_fleet(client), "A05-BS1")
    assert bs1["lifecycle_id"] == "A05-BS1-LC2" and bs1["health"] == "NORMAL"
    assert [lc["status"] for lc in bs1["lifecycles"]] == ["RETIRED", "ACTIVE"]
    refs = client.get("/api/components/A05-BS1/baselines").json()
    verified = {b["lifecycle_id"] for b in refs if b["kind"] == "VERIFIED_HEALTHY"}
    assert verified == {"A05-BS1-LC1", "A05-BS1-LC2"}


def test_maintenance_outcomes_drive_the_workflow(env):
    client, _, results = env
    assert results["A05"].workflows == {"WF-A05-SIM-ME-0001": "NORMAL_MONITORING"}
    assert results["A10"].workflows == {"WF-A10-SIM-ME-0001": "REVIEW_REQUIRED"}  # deterioration
    wfs = client.get("/api/maintenance-workflows", params={"component_id": "A10-BS1"}).json()
    assert wfs[0]["state"] == "REVIEW_REQUIRED"
    assert [t["by"] for t in wfs[0]["transitions"]][-1] == "system:maintenance-impact"


def test_health_report_carries_the_evidence_trail(env):
    client, _, _ = env
    r = client.get("/api/components/A02-BS1/health")
    assert r.status_code == 200, r.text
    rep = r.json()
    d = rep["decision"]
    assert rep["is_simulated"] and d["health_state"] == "CRITICAL" and d["lifecycle_id"] == "A02-BS1-LC1"
    sources = {e["source"] for e in rep["evidence"]}
    assert {"STATISTIC", "RULE"} <= sources
    assert d["evidence_ids"] == [e["evidence_id"] for e in rep["evidence"]]
    assert any("demo-engineer (SIMULATED)" in e["summary"]["en"] for e in rep["evidence"])
    assert d["meta"]["is_simulated"] and d["meta"]["model_version"] == "evidence-fusion@1.0.0"
    assert "pdm-rules@" in d["meta"]["config_version"]
    impact = client.get("/api/components/A10-BS1/health").json()["evidence"]
    assert any(e["source"] == "MAINTENANCE" and "DETERIORATED" in e["summary"]["en"] for e in impact)


def test_alarm_review_is_recorded(env):
    client, factory, _ = env
    alarm = client.get("/api/alarms", params={"component_id": "A02-BS1", "status": "RAISED"}).json()[0]
    aid = alarm["alarm_id"]
    r = client.post(f"/api/alarms/{aid}/acknowledge", {"comment": "checking the axis"}, role="maintenance")
    assert r.status_code == 200 and r.json()["status"] == "ACKNOWLEDGED"
    r = client.post(
        f"/api/alarms/{aid}/resolve", {"comment": "lubricated, re-check tomorrow"}, role="maintenance"
    )
    assert r.status_code == 200 and r.json()["resolution_comment"] == "lubricated, re-check tomorrow"
    with factory() as s:
        actions = s.scalars(select(AuditRecord.action).where(AuditRecord.object_id == aid)).all()
    assert actions[0] == "alarm.raise" and actions[-2:] == ["alarm.acknowledge", "alarm.resolve"]
    assert _component(_fleet(client), "A02-BS1")["open_alarms"] == 0


def test_references_are_created_only_by_the_labeled_demo_engineer(env):
    _, factory, _ = env
    with factory() as s:
        actors = set(s.scalars(select(AuditRecord.actor).where(AuditRecord.action == "baseline.verify")))
    assert actors == {"demo-engineer (SIMULATED)"}


def test_stale_or_unreferenced_components_are_unknown(env):
    _, factory, _ = env
    with factory() as s:
        svc = FleetHealthService(s)
        evals, refs = svc._evaluate("A07-BS1")
        last = evals[-1].window.end
        assert svc._assess("A07-BS1", evals, refs, last).health.value == "NORMAL"
        late = svc._assess("A07-BS1", evals, refs, last + timedelta(hours=30))
        assert late.health.value == "UNKNOWN" and "30 h" in late.reason.en
        assert svc._assess("A07-BS1", evals, {}, last).health.value == "UNKNOWN"


def test_viewer_is_required(env):
    client, _, _ = env
    assert client.http.get("/api/fleet").status_code == 401
