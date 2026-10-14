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
                pc.Stage(stage_id="xgb", algorithm="xgboost"),
            ]
        }
    )
    res, _ = pc.compile_config(session, cid, content)
    by = {s.stage_id: s for s in res.stages}
    assert res.ok and by["rules"].effective and by["features"].effective
    assert not by["t2"].effective and not by["lstm"].effective  # no implementation: interface only
    assert not by["xgb"].effective and {i.code for i in res.issues} >= {
        "NOT_IMPLEMENTED",
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
