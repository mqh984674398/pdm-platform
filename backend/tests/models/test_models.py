"""T022: leakage-safe splits, model training, versioned registry and the trained-model operator."""

from dataclasses import replace

import numpy as np
import pytest

from app.equipment.schemas import ComponentType
from app.monitoring.features.definitions import FEATURE_SETS
from app.prediction.models.dataset import (
    LeakageError,
    assert_no_leakage,
    feature_names,
    group_folds,
    matrix,
    time_split,
)
from app.prediction.models.operator import TrainedModelOperator
from app.prediction.models.registry import ModelRecord, ModelRegistry, ModelRegistryError, stamp
from app.prediction.models.train import KINDS, degraded_probability, fit, metrics
from app.prediction.routing.operator import OperatorInput
from app.prediction.routing.router import Router, default_registry
from app.prediction.routing.templates import DEFAULT_TEMPLATES
from app.simulation.training_data import scenario_samples

from ..baselines.conftest import db, factory  # noqa: F401
from ..equipment.conftest import DATA
from ..routing.test_routing import sampling
from ..rules.conftest import after_reference, references

BS = ComponentType.BALL_SCREW
FS = FEATURE_SETS[BS]
REF = f"{FS.feature_set}@{FS.version}"


@pytest.fixture(scope="module")
def ball_screw():
    out = []
    for sid in ("S01", "S04", "S12"):
        out += [s for s in scenario_samples(DATA, sid) if s.vector.feature_ref == REF]
    return out


def test_labels_come_from_simulated_truth_and_both_classes_exist(ball_screw):
    labels = {s.label for s in ball_screw}
    assert labels == {0, 1}
    assert not any(s.label for s in ball_screw if s.scenario == "S01")  # healthy scenario
    assert all(s.vector.is_simulated for s in ball_screw)


def test_grouped_folds_never_split_an_installation(ball_screw):
    folds = group_folds(ball_screw, 3, seed=1)
    assert folds
    for tr, te in folds:
        assert_no_leakage(ball_screw, tr, te, by_group=True)
    assert sorted(i for _, te in folds for i in te) == list(range(len(ball_screw)))


def test_leaky_splits_are_refused(ball_screw):
    idx = list(range(len(ball_screw)))
    with pytest.raises(LeakageError, match="both"):
        assert_no_leakage(ball_screw, idx[::2], idx[1::2], by_group=True)  # interleaved windows
    with pytest.raises(LeakageError):
        assert_no_leakage(ball_screw, idx[:10], idx[5:15])  # shared windows
    # time split without the embargo: a test window touches training
    tr, te = time_split(ball_screw, 360.0, embargo_h=0.0)
    with pytest.raises(LeakageError, match="not after training"):
        assert_no_leakage(ball_screw, tr, te, by_group=False, embargo_h=24.0)
    tr, te = time_split(ball_screw, 360.0, embargo_h=24.0)
    assert_no_leakage(ball_screw, tr, te, by_group=False, embargo_h=24.0)


@pytest.mark.parametrize("kind", KINDS)
def test_training_is_deterministic_and_separates_the_classes(ball_screw, kind):
    feats = feature_names(ball_screw)
    x, y = matrix(ball_screw, feats)
    tr, te = time_split(ball_screw, 360.0)
    a = degraded_probability(fit(kind, x[tr], y[tr], 7), x[te])
    b = degraded_probability(fit(kind, x[tr], y[tr], 7), x[te])
    assert np.array_equal(a, b)
    m = metrics(y[te], a)
    assert m["n"] == len(te) and m["tp"] + m["fn"] == m["positives"]
    assert m["roc_auc"] is not None and m["roc_auc"] > 0.7  # simulated data, not real accuracy


def test_metrics_without_both_classes_report_no_auc():
    assert metrics([0, 0, 0], [0.1, 0.2, 0.9])["roc_auc"] is None


def _record(model_id: str, feats: list[str]) -> ModelRecord:
    return ModelRecord(
        model_id=model_id, kind="decision_tree", component_type=BS, feature_ref=REF, features=feats,
        label_definition="SIMULATED truth", training_scenarios=["S01", "S04", "S12"], params={}, seed=7,
        metrics={}, is_simulated=True, created_at=stamp(),
    )  # fmt: skip


@pytest.fixture(scope="module")
def trained(ball_screw):
    feats = feature_names(ball_screw)
    x, y = matrix(ball_screw, feats)
    return fit("decision_tree", x, y, 7), feats


def test_registry_round_trip_is_immutable_and_refuses_tampering(tmp_path, trained):
    model, feats = trained
    reg = ModelRegistry(tmp_path)
    rec = reg.save(model, _record("dt-ball-screw@1.0.0", feats))
    assert len(rec.sha256) == 64
    loaded, back = reg.load("dt-ball-screw@1.0.0")
    assert back == rec and back.features == feats
    with pytest.raises(ModelRegistryError, match="immutable"):
        reg.save(model, _record("dt-ball-screw@1.0.0", feats))
    with pytest.raises(ModelRegistryError, match="unknown"):
        reg.load("dt-ball-screw@9.9.9")
    p = tmp_path / "dt-ball-screw@1.0.0.pkl"
    p.write_bytes(p.read_bytes() + b"x")
    with pytest.raises(ModelRegistryError, match="refusing"):
        reg.load("dt-ball-screw@1.0.0")


def test_trained_model_routes_as_uncalibrated_class_probability(db, trained):  # noqa: F811
    model, feats = trained
    op = TrainedModelOperator(model, _record("dt-ball-screw@1.0.0", feats))
    reg = default_registry()
    reg.register(op)
    tpl = DEFAULT_TEMPLATES[BS]
    templates = {**DEFAULT_TEMPLATES, BS: replace(tpl, operator_ids=(*tpl.operator_ids, op.spec.operator_id))}
    ref = references(db, "S04")["M01-BS1"]
    v = after_reference("S04", "M01-BS1")[-1]
    results = Router(reg, templates).route(
        OperatorInput("M01-BS1", BS, v, ref, sampling("S04", "M01-BS1", v))
    )
    r = next(r for r in results if r.operator_id == "dt-ball-screw@1.0.0")
    assert r.kind == "class_probability"
    assert r.calibrated is False
    assert set(r.probabilities) == {"healthy", "degraded"}
    assert abs(sum(r.probabilities.values()) - 1.0) < 1e-9
    assert "SIMULATED" in op.spec.model_version
