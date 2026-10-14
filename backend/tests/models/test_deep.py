# ruff: noqa: E501
"""D-046: the deep sequence model interface (LSTM, D-RCNN). A numpy test double stands in for a real
backend; no deep learning framework is involved and nothing here trains a production model."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.core.schemas import TimeWindow
from app.equipment.schemas import ComponentType
from app.monitoring.schemas import FeatureVector
from app.prediction.models import deep
from app.prediction.models.registry import ModelRegistry, ModelRegistryError
from app.prediction.routing.operator import OperatorInput

T0 = datetime(2026, 1, 1, tzinfo=UTC)
BS = ComponentType.BALL_SCREW
TRUTH = "SIMULATED truth: degraded after the injected fault start"


class Logistic(deep.DeepModelAdapter):
    """Mean over the sequence, one logistic regression by gradient descent. Test double only."""

    family = "lstm"
    component_types = (BS,)
    contract = deep.InputContract(
        kind=deep.InputKind.WINDOW_SEQUENCE, features=["a", "b"], sequence_length=4,
        min_training_samples=100, min_fault_samples=10,
    )  # fmt: skip

    def available(self):
        return None

    def default_params(self):
        return {"lr": 0.5, "steps": 200}

    def search_space(self):
        return {"lr": [0.01, 0.5], "steps": [20, 200]}

    def fit(self, data, params, seed, base=None):
        x = data.x.mean(axis=1)
        w = np.zeros(x.shape[1] + 1) if base is None else base.copy()
        xb = np.hstack([x, np.ones((len(x), 1))])
        for _ in range(params["steps"]):
            p = 1 / (1 + np.exp(-xb @ w))
            w -= params["lr"] * xb.T @ (p - data.y) / len(x)
        return w

    def predict_degraded(self, model, x):
        xb = np.hstack([x.mean(axis=1), np.ones((len(x), 1))])
        return 1 / (1 + np.exp(-xb @ model))


def dataset(n_groups=10, per=30, seed=0, label=TRUTH):
    rng = np.random.default_rng(seed)
    xs, ys, gs = [], [], []
    for g in range(n_groups):
        for _ in range(per):
            y = int(rng.random() < 0.3)
            xs.append(rng.normal(loc=2.0 * y, scale=0.7, size=(4, 2)))
            ys.append(y)
            gs.append(f"S{g:02d}/LC")
    return deep.TrainingData(np.array(xs), np.array(ys), gs, label, ["S01"], True)


@pytest.fixture
def reg(tmp_path):
    return ModelRegistry(tmp_path / "models")


def test_placeholders_are_unavailable_and_never_train(reg):
    status = deep.adapter_status()
    assert status["lstm"] and status["drcnn"]  # no backend is shipped
    with pytest.raises(deep.DeepModelError):
        deep.train_deep(
            reg, deep.ADAPTERS["lstm"], dataset(), version="1.0.0", component_type=BS, feature_ref="f@1"
        )


def test_train_validate_store_then_fine_tune_and_tune(reg):
    a = Logistic()
    rec = deep.train_deep(reg, a, dataset(), version="1.0.0", component_type=BS, feature_ref="f@1", seed=1)
    assert rec.model_id == "lstm@1.0.0" and rec.metrics["validation"]["roc_auc"] >= 0.8 and rec.sha256
    assert rec.params["fine_tuned_from"] is None and rec.metrics["held_out_groups"]
    tuned = deep.train_deep(reg, a, dataset(seed=3), version="1.1.0", component_type=BS, feature_ref="f@1",
                            seed=2, base_model_id=rec.model_id, params={"steps": 50})  # fmt: skip
    assert tuned.params["fine_tuned_from"] == "lstm@1.0.0"
    with pytest.raises(ModelRegistryError):  # versions are immutable
        deep.train_deep(reg, a, dataset(), version="1.0.0", component_type=BS, feature_ref="f@1")
    trials = deep.tune(a, dataset(), trials=4, seed=0)
    assert len(trials) == 4 and trials == sorted(trials, key=lambda t: -t[1])


def test_gates_refuse_bad_labels_thin_data_and_wrong_shape(reg):
    a = Logistic()
    kw = dict(version="2.0.0", component_type=BS, feature_ref="f@1")
    with pytest.raises(deep.DeepModelError, match="recorded truth"):
        deep.train_deep(reg, a, dataset(label="derived from health states"), **kw)
    with pytest.raises(deep.DeepModelError, match="not enough labelled data"):
        deep.train_deep(reg, a, dataset(n_groups=3, per=10), **kw)
    bad = dataset()
    with pytest.raises(deep.DeepModelError, match="must be"):
        deep.train_deep(
            reg, a, deep.TrainingData(bad.x[:, :2], bad.y, bad.groups, TRUTH, ["S01"], True), **kw
        )
    with pytest.raises(deep.DeepModelError, match="does not apply"):
        deep.train_deep(
            reg, a, dataset(), version="2.0.0", component_type=ComponentType.CAM, feature_ref="f@1"
        )


def vec(i, **vals):
    return FeatureVector(
        component_id="C1", lifecycle_id="L1", regime_id=None, regime_status="KNOWN", catalog_id=None,
        feature_ref="f@1", window=TimeWindow(start=T0 + timedelta(hours=i), end=T0 + timedelta(hours=i + 1)),
        source_signals=[], values=vals, is_simulated=True,
    )  # fmt: skip


def test_operator_needs_the_whole_sequence(reg):
    a = Logistic()
    rec = deep.train_deep(reg, a, dataset(), version="1.0.0", component_type=BS, feature_ref="f@1", seed=1)
    model, _ = reg.load(rec.model_id)
    op = deep.DeepModelOperator(a, model, rec)
    hist = tuple(vec(i, a=2.0, b=2.0) for i in range(3))
    ok = op.run(OperatorInput("C1", BS, vec(3, a=2.0, b=2.0), history=hist))
    assert ok.kind == "class_probability" and ok.probabilities["degraded"] > 0.5 and not ok.calibrated
    short = op.run(OperatorInput("C1", BS, vec(3, a=2.0, b=2.0), history=hist[:1]))
    assert short.kind == "unsupported" and short.reason.value == "INSUFFICIENT_DATA"
    gap = op.run(OperatorInput("C1", BS, vec(3, a=None, b=2.0), history=hist))
    assert gap.kind == "unsupported" and gap.reason.value == "DATA_QUALITY"


def test_register_adapter_rules():
    class Bad(Logistic):
        family = "Bad Family"

    with pytest.raises(deep.DeepModelError):
        deep.register_adapter(Bad())
    deep.register_adapter(Logistic(), replace=True)  # a real backend replaces the placeholder
    assert deep.adapter_status()["lstm"] is None
    with pytest.raises(deep.DeepModelError):
        deep.register_adapter(Logistic())  # a working adapter is not silently overwritten
    deep.register_adapter(deep.LstmPlaceholder(), replace=True)  # restore for other tests
