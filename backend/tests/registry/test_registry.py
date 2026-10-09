"""T026: champion/challenger registry, gated promotion, one-step rollback, training-data guard."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.main  # noqa: F401  (registers tables)
from app.core.audit import entries
from app.core.db import Base, get_session
from app.core.registry import DeploymentRegistry, RegistryError, RegistryPermissionError
from app.core.security import Principal, Role
from app.datasource.query_service.sources import DataSourceRegistry
from app.decision.config import KIND, DecisionConfig, active
from app.equipment.schemas import ComponentType
from app.main import create_app
from app.optimization.deployment import check_training_sources, evaluate_config, propose_model
from app.optimization.suite import demo_suite
from app.prediction.models.registry import ModelRecord
from app.simulation.demo_pipeline import DEMO_FLEET, add_demo_source, demo_machines, run_pipeline
from app.simulation.golden import DATA_DIR

from ..query_service.conftest import Client

ENG = Principal(user_id="eng", role=Role.ENGINEER)
ADMIN = Principal(user_id="adm", role=Role.ADMIN)
SELECTED = ("A02", "A03")  # S04 drift, S03 aging


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'r.db'}")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    engine.dispose()


def ev(gate: bool, base: str | None) -> dict:
    return {"gate_passed": gate, "baseline_version": base}


# --- core registry ----------------------------------------------------------------------------------


def test_promotion_needs_gate_admin_comment_and_current_baseline(db):
    reg = DeploymentRegistry(db, "demo")
    seed = reg.seed({"v": 1}, ADMIN, True)
    assert seed.status == "CHAMPION" and seed.version_id == "demo.v1"
    with pytest.raises(RegistryError, match="gate_passed"):
        reg.propose({"v": 2}, {}, ENG, "x", True)
    failed = reg.propose({"v": 2}, ev(False, seed.version_id), ENG, "x", True)
    with pytest.raises(RegistryError, match="did not pass"):
        reg.promote(failed.version_id, ADMIN, "go")
    good = reg.propose({"v": 3}, ev(True, seed.version_id), ENG, "better", True)
    with pytest.raises(RegistryPermissionError):
        reg.promote(good.version_id, ENG, "go")
    with pytest.raises(RegistryError, match="comment"):
        reg.promote(good.version_id, ADMIN, " ")
    stale = reg.propose({"v": 4}, ev(True, "demo.v0"), ENG, "old", True)
    with pytest.raises(RegistryError, match="evaluate it again"):
        reg.promote(stale.version_id, ADMIN, "go")
    p = reg.promote(good.version_id, ADMIN, "approved after review")
    assert p.status == "CHAMPION" and p.previous_version_id == "demo.v1" and p.decided_by == "adm"
    assert reg.get("demo.v1").status == "RETIRED"
    assert reg.champion().payload == {"v": 3}
    with pytest.raises(RegistryError, match="not a candidate"):
        reg.promote(good.version_id, ADMIN, "again")
    actions = [e.action for e in entries(db, object_type="demo")]
    assert actions.count("registry.propose") == 3 and "registry.promote" in actions


def test_rollback_restores_the_previous_champion_in_one_action(db):
    reg = DeploymentRegistry(db, "demo")
    with pytest.raises(RegistryError):
        reg.rollback(ENG, "nothing yet")
    seed = reg.seed({"v": 1}, ADMIN, True)
    with pytest.raises(RegistryError, match="no previous"):
        reg.rollback(ENG, "nothing to restore")
    good = reg.propose({"v": 2}, ev(True, seed.version_id), ENG, "x", True)
    reg.promote(good.version_id, ADMIN, "ok")
    with pytest.raises(RegistryPermissionError):
        reg.rollback(Principal(user_id="v", role=Role.VIEWER), "no")
    rb = reg.rollback(ENG, "alarm flood after promotion")
    assert rb.status == "CHAMPION" and rb.payload == {"v": 1} and rb.previous_version_id == good.version_id
    assert reg.get(good.version_id).status == "RETIRED"
    assert [v.version_id for v in reg.history()] == ["demo.v1", "demo.v2", "demo.v3"]  # nothing deleted
    assert any(e.action == "registry.rollback" for e in entries(db, object_type="demo"))


def test_reject_keeps_the_candidate_for_the_record(db):
    reg = DeploymentRegistry(db, "demo")
    seed = reg.seed({"v": 1}, ADMIN, True)
    c = reg.propose({"v": 2}, ev(True, seed.version_id), ENG, "x", True)
    assert reg.reject(c.version_id, ENG, "not now").status == "REJECTED"
    assert reg.champion().version_id == seed.version_id


# --- Path C: trained models -----------------------------------------------------------------------


def record(
    model_id: str, auc: float, f1: float, label: str = "SIMULATED truth: max(friction_factor) >= 1.15"
) -> ModelRecord:
    return ModelRecord(
        model_id=model_id,
        kind="xgboost",
        component_type=ComponentType.BALL_SCREW,
        feature_ref="ball_screw@1.1.0",
        features=["a"],
        label_definition=label,
        training_scenarios=["S04"],
        params={},
        seed=7,
        metrics={"grouped_cv": {"roc_auc": auc, "f1": f1}, "time_split": None},
        is_simulated=True,
        created_at=datetime.now(UTC),
        sha256="x",
    )


@pytest.mark.parametrize(
    "label",
    [
        "health state WARNING or worse",
        "ADAPTIVE baseline deviation",
        "online windows after the reference",
        "x",
    ],
)
def test_training_labels_must_be_recorded_truth(label):
    with pytest.raises(RegistryError):
        check_training_sources(record("xgb-ball-screw@9.0.0", 0.9, 0.9, label))


def test_model_candidates_are_gated_on_grouped_validation(db):
    weak = propose_model(db, record("xgb-ball-screw@1.0.0", 0.6, 0.5), ENG, "try")
    assert not weak.evaluation["gate_passed"] and "AUC" in weak.evaluation["reasons"][0]
    good = propose_model(db, record("xgb-ball-screw@1.1.0", 0.96, 0.87), ENG, "retrained")
    assert good.evaluation["gate_passed"] and good.evaluation["baseline_version"] is None
    reg = DeploymentRegistry(db, "component-model:BALL_SCREW")
    reg.promote(good.version_id, ADMIN, "first model")
    worse = propose_model(db, record("xgb-ball-screw@1.2.0", 0.9, 0.8), ENG, "retrained")
    assert not worse.evaluation["gate_passed"] and "champion" in worse.evaluation["reasons"][0]
    better = propose_model(db, record("xgb-ball-screw@1.3.0", 0.97, 0.9), ENG, "retrained")
    assert better.evaluation["gate_passed"] and better.evaluation["baseline_version"] == good.version_id


# --- decision configuration on the replayed SIMULATED pipeline -------------------------------------


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    engine = create_engine(f"sqlite:///{tmp_path_factory.mktemp('reg') / 'app.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    machines = demo_machines(DATA_DIR, [r for r in DEMO_FLEET if r[0] in SELECTED])
    sources = DataSourceRegistry()
    add_demo_source(sources, machines)
    with factory() as s:
        run_pipeline(s, sources, machines)

    def session():
        with factory() as s:
            yield s

    application = create_app(sources=sources)
    application.dependency_overrides[get_session] = session
    yield Client(application), factory
    engine.dispose()


def test_config_gate_compares_candidate_and_champion_on_replay(env):
    _, factory = env
    with factory() as s:
        suite = demo_suite(s, DATA_DIR)
        base = active(s)
        loose = DecisionConfig(
            base.rules, replace(base.policy, max_rate_per_day=0.0, version="aging-off"), None
        )
        e = evaluate_config(s, suite, loose)  # aging grading effectively off: S03 escalates again
        assert not e["gate_passed"] and e["candidate"]["within"] < e["champion"]["within"]
        assert e["baseline_version"] == f"{KIND}.v1" and e["is_simulated"]


def test_promote_and_roll_back_a_decision_config_through_the_api(env):
    client, _ = env
    from app.optimization import service as opt_service

    opt_service._LATEST.clear()
    r = client.post("/api/optimization/runs", {"candidates": 6, "seed": 0}, role="engineer")
    assert r.status_code == 200, r.text
    run = r.json()
    proposals = []
    for c in run["candidates"]:
        p = client.post(
            "/api/registry/decision-config/candidates",
            {"candidate_id": c["candidate_id"], "comment": "from replay"},
            role="engineer",
        )
        assert p.status_code == 200, p.text
        proposals.append(p.json())
    assert (
        client.post(
            "/api/registry/decision-config/candidates",
            {"candidate_id": "Z9", "comment": "x"},
            role="engineer",
        ).status_code
        == 409
    )
    passed = [p for p in proposals if p["evaluation"]["gate_passed"]]
    failed = [p for p in proposals if not p["evaluation"]["gate_passed"]]
    for p in failed:
        bad = client.post(
            f"/api/registry/versions/{p['version_id']}/promote", {"comment": "go"}, role="admin"
        )
        assert bad.status_code == 409 and bad.json()["code"] == "registry_refused"
    assert passed, "at least one replayed candidate keeps every window within and none lower"
    target = passed[0]
    v = target["version_id"]
    assert (
        client.post(f"/api/registry/versions/{v}/promote", {"comment": "go"}, role="engineer").status_code
        == 403
    )
    ok = client.post(f"/api/registry/versions/{v}/promote", {"comment": "approved"}, role="admin")
    assert ok.status_code == 200, ok.text
    tag = target["payload"]["rules"]["version"] if "+" in target["payload"]["rules"]["version"] else None
    fleet = client.get("/api/fleet").json()
    if tag:
        assert fleet["rules_version"].startswith(f"pdm-rules@{tag}")
    hist = client.get("/api/registry/versions", params={"kind": KIND}).json()
    assert [h["status"] for h in hist if h["version_id"] == f"{KIND}.v1"] == ["RETIRED"]
    rb = client.post("/api/registry/rollback", {"kind": KIND, "comment": "restore"}, role="engineer")
    assert rb.status_code == 200, rb.text
    assert client.get("/api/fleet").json()["rules_version"].startswith("pdm-rules@1.0.0+")
    assert rb.json()["payload"] == hist[0]["payload"]
    kinds = {k["kind"]: k for k in client.get("/api/registry/kinds").json()}
    assert kinds[KIND]["champion"]["version_id"] == rb.json()["version_id"]
