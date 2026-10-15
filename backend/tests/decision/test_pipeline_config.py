# ruff: noqa: E501, E731
"""D-044: prediction configuration versions, compile, validation, publish and activate."""

import pytest

from app.core.security import Principal, Role
from app.datasource.query_service.sources import DataSourceRegistry
from app.decision import config_validation as cv
from app.decision import pipeline_config as pc
from app.simulation.demo_pipeline import add_demo_source

ADMIN = Principal(user_id="admin1", role=Role.ADMIN)
ENG = Principal(user_id="eng1", role=Role.ENGINEER)


def good(**kw) -> pc.ConfigContent:
    return pc.ConfigContent(
        pipeline=[
            pc.Stage(stage_id="rules", algorithm="engineering-rules"),
            pc.Stage(stage_id="features", algorithm="feature-engineering"),
        ],
        **kw,
    )


@pytest.fixture
def ctx(replay):
    svc, machines = replay
    sources = DataSourceRegistry()
    add_demo_source(sources, machines)
    comp = next(c for c in svc.equipment.components() if c.type.value == "BALL_SCREW")
    yield svc.session, sources, comp.component_id
    svc.session.rollback()


def test_compile_reports_unmet_prerequisites_instead_of_enabling(ctx):
    session, _, cid = ctx
    content = good()
    content = content.model_copy(
        update={
            "pipeline": [
                *content.pipeline,
                pc.Stage(stage_id="t2", algorithm="mahalanobis-t2"),
                pc.Stage(stage_id="lstm", algorithm="lstm"),
                pc.Stage(stage_id="cnn", algorithm="drcnn"),
                pc.Stage(stage_id="xgb", algorithm="xgboost"),
            ]
        }
    )
    res, _ = pc.compile_config(session, cid, content)
    by = {s.stage_id: s for s in res.stages}
    assert res.ok and by["rules"].effective and by["features"].effective
    assert by["t2"].effective  # unsupervised: needs no labels or deployed model
    assert not by["lstm"].effective and not by["cnn"].effective  # interface ready, no backend adapter
    assert not by["xgb"].effective and {i.code for i in res.issues} >= {
        "NO_BACKEND",
        "NO_VALIDATED_MODEL",
    }


def test_compile_errors(ctx):
    session, _, cid = ctx
    assert not pc.compile_config(session, cid, pc.ConfigContent())[0].ok  # empty pipeline
    no_rules = pc.ConfigContent(pipeline=[pc.Stage(stage_id="f", algorithm="feature-engineering")])
    assert "NO_RULES" in {i.code for i in pc.compile_config(session, cid, no_rules)[0].issues}
    bad = good(relationship=pc.Relationship(type=pc.RelationType.SHARED_DRIVETRAIN, members=["nope"]))
    assert "BAD_RELATION_MEMBER" in {i.code for i in pc.compile_config(session, cid, bad)[0].issues}
    assert not pc.compile_config(session, "ghost", good())[0].ok
    with pytest.raises(ValueError):
        pc.Criteria(safety_first=False)  # the safety floor cannot be switched off


def test_lifecycle_validate_publish_activate_and_immutability(ctx):
    session, sources, cid = ctx
    store = pc.PredictionConfigStore(session)
    with pytest.raises(pc.PredictionConfigPermissionError):
        store.create_draft(cid, good(), ENG)
    d = store.create_draft(cid, good(), ADMIN)
    assert (d.config_id, d.status.value, d.version) == (f"{cid}@v1", "DRAFT", 1)
    with pytest.raises(pc.PredictionConfigError):  # not validated yet
        store.publish(d.config_id, ADMIN, "go")
    checks = cv.run_all(session, sources, d)
    by = {c.name: c for c in checks}
    assert by["compile"].ok and by["simulation"].ok and by["simulation"].details["simulated"]
    assert by["data"].ok, by["data"]
    assert by["replay"].ok, by["replay"]
    v = store.save_validation(d.config_id, checks, ADMIN)
    assert v.status.value == "VALIDATED"
    edited = store.update_draft(d.config_id, good(display=pc.Display(trend=False)), ADMIN)
    assert edited.status.value == "DRAFT" and not edited.validation  # an edit voids validation
    store.save_validation(d.config_id, checks, ADMIN)
    with pytest.raises(pc.PredictionConfigError):
        store.publish(d.config_id, ADMIN, " ")
    p = store.publish(d.config_id, ADMIN, "first release")
    assert p.status.value == "PUBLISHED" and p.content_hash == pc.content_hash(p.content)
    with pytest.raises(pc.PredictionConfigError):
        store.update_draft(d.config_id, good(), ADMIN)  # published = immutable
    with pytest.raises(pc.PredictionConfigError):
        store.delete_draft(d.config_id, ADMIN)
    assert store.activate(d.config_id, ADMIN).active
    v2 = store.clone(d.config_id, ADMIN)
    assert v2.version == 2 and v2.content == p.content and not v2.active
    store.save_validation(v2.config_id, checks, ADMIN)
    store.publish(v2.config_id, ADMIN, "second")
    store.activate(v2.config_id, ADMIN)
    assert store.active(cid).config_id == v2.config_id and not store.get(d.config_id).active
    store.deactivate(cid, ADMIN)
    assert store.active(cid) is None


def test_a_failed_check_blocks_validation(ctx):
    session, sources, cid = ctx
    store = pc.PredictionConfigStore(session)
    d = store.create_draft(cid, pc.ConfigContent(), ADMIN)  # empty pipeline: compile fails
    v = store.save_validation(d.config_id, cv.run_all(session, sources, d), ADMIN)
    assert v.status.value == "DRAFT" and not next(c for c in v.validation if c.name == "compile").ok


# --- D-046: matching, plugins and the engine reading the active configuration ---------------------------


def _activate(session, sources, cid, content):
    store = pc.PredictionConfigStore(session)
    d = store.create_draft(cid, content, ADMIN)
    # the data and replay checks are covered above; here only the active version matters
    checks = [
        pc.CheckResult(name=n, ok=True, summary=pc._t("ok", "ok"))
        for n in ("data", "compile", "replay", "simulation")
    ]
    store.save_validation(d.config_id, checks, ADMIN)
    store.publish(d.config_id, ADMIN, "test")
    return store.activate(d.config_id, ADMIN)


def test_recommendation_matches_type_and_signals(ctx):
    session, _, cid = ctx
    r = pc.recommend_config(session, cid)
    algos = [s.algorithm for s in r.content.pipeline]
    assert algos[:3] == ["engineering-rules", "feature-engineering", "mahalanobis-t2"]
    assert "xgboost" in algos and "lstm" in algos and "drcnn" not in algos  # no vibration signal mapped
    assert r.match.component_type == "BALL_SCREW" and r.match.constraints
    assert r.compile.ok and {"SPEED", "TORQUE"} >= {q.value for q in r.available_quantities}
    assert not r.missing_quantities


def test_plugin_contract():
    from app.decision import plugins as pl
    from app.decision.schemas import EvidenceType, HealthState

    spec = pl.PluginSpec(plugin_id="my-check", version="1.0.0", name=pc._t("自定义", "Custom"),
                         evidence_type=EvidenceType.ANOMALY, input_quantities=[pc.Q.TORQUE],
                         description=pc._t("示例", "example"))  # fmt: skip
    ok = lambda x: pl.PluginEvidence(raw_value=sum(x["TORQUE"]), reason=pc._t("正常", "fine"))  # noqa: E731
    pl.register_plugin(spec, ok, {"TORQUE": [1.0, 2.0]})
    try:
        with pytest.raises(pl.PluginError):  # versions are immutable
            pl.register_plugin(spec, ok, {"TORQUE": [1.0]})
        loud = spec.model_copy(update={"version": "1.0.1"})
        with pytest.raises(pl.PluginError, match="at most WATCH"):
            pl.register_plugin(
                loud,
                lambda x: pl.PluginEvidence(
                    raw_value=1, proposed_severity=HealthState.CRITICAL, reason=pc._t("x", "x")
                ),
                {"TORQUE": [1.0]},
            )
        with pytest.raises(pl.PluginError):
            pl.register_plugin(
                spec.model_copy(update={"version": "2.0.0", "evidence_type": EvidenceType.SAFETY}),
                ok,
                {"TORQUE": [1.0]},
            )
        with pytest.raises(pl.PluginError):
            pl.register_plugin(
                spec.model_copy(update={"version": "2.0.1"}), lambda x: 1 / 0, {"TORQUE": [1.0]}
            )
    finally:
        pl.PLUGINS.pop(spec.ref, None)


def test_active_configuration_drives_the_engine(replay):
    from app.decision.fleet import FleetHealthService
    from app.decision.schemas import EvidenceType, HealthState

    svc, machines = replay
    session = svc.session
    try:
        overview = svc.overview()
        comps = [c for m in overview.machines for c in m.components]
        bad = [c for c in comps if c.health in (HealthState.WARNING, HealthState.CRITICAL)]
        a = next((c for c in bad if not c.drive_chain_id), None)
        assert a is not None and len(bad) >= 2, [(c.component_id, c.health.value) for c in comps]
        b = next(c for c in bad if c.component_id != a.component_id)
        assert FleetHealthService(session).report(a.component_id).config_version is None
        # a configuration with T²: evidence appears, labelled as the configuration's
        content = good(
            relationship=pc.Relationship(type=pc.RelationType.SHARED_SIGNAL, members=[b.component_id],
                                         affects_status_display=True, affects_common_cause=True),
        ).model_copy(update={"pipeline": [*good().pipeline, pc.Stage(stage_id="t2", algorithm="mahalanobis-t2")]})  # fmt: skip
        _activate(session, DataSourceRegistry(), a.component_id, content)
        rep = FleetHealthService(session).report(a.component_id)
        assert rep.config_version == f"{a.component_id}@v1" and rep.display.trend
        t2 = [e for e in rep.evidence if e.result_ref == "mahalanobis-t2"]
        assert t2 and t2[0].evidence_type == EvidenceType.ANOMALY and t2[0].calibration
        assert rep.common_cause and rep.common_cause.drive_chain_id.startswith("SHARED_SIGNAL:")
        assert {r.component_id for r in rep.related} == {b.component_id}
        # statistical evidence switched off: it no longer decides, and the report says so
        no_stat = good(
            criteria=pc.Criteria(allowed_evidence_types=[EvidenceType.SAFETY, EvidenceType.ANOMALY])
        )
        store = pc.PredictionConfigStore(session)
        store.deactivate(a.component_id, ADMIN)
        _activate(session, DataSourceRegistry(), a.component_id, no_stat)
        rep2 = FleetHealthService(session).report(a.component_id)
        stat = [e for e in rep2.evidence if e.evidence_type == EvidenceType.STATISTICAL]
        assert stat and not any(e.applicable for e in stat)
        assert rep2.decision.health_state != a.health or a.health == HealthState.UNKNOWN
        with pytest.raises(ValueError):
            pc.Criteria(allowed_evidence_types=[EvidenceType.STATISTICAL])  # safety cannot be excluded
    finally:
        session.rollback()


def test_algorithm_models_listing_shows_where_each_algorithm_runs(ctx):
    from app.api.pipeline_config import algorithm_models

    session, sources, cid = ctx
    store = pc.PredictionConfigStore(session)
    d = store.create_draft(cid, good(), ADMIN)
    before = {e.spec.algorithm_id: e for e in algorithm_models(ADMIN, session).algorithms}
    assert set(before) == set(pc.CATALOG)
    assert before["engineering-rules"].draft_uses == 1 and not before["engineering-rules"].active_uses
    store.save_validation(d.config_id, cv.run_all(session, sources, d), ADMIN)
    store.publish(d.config_id, ADMIN, "go")
    store.activate(d.config_id, ADMIN)
    out = algorithm_models(ADMIN, session)
    after = {e.spec.algorithm_id: e for e in out.algorithms}
    use = after["engineering-rules"].active_uses[0]
    assert (use.component_id, use.config_id, use.enabled) == (cid, d.config_id, True)
    assert after["engineering-rules"].draft_uses == 0
    assert {a.family for a in out.deep_adapters}  # LSTM / D-RCNN adapters are listed with their availability
