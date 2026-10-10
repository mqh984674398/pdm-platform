"""T021: operator specs, component templates and routing with eligibility, timeout and fallback."""

import time

import numpy as np
import pytest

from app.equipment.schemas import ComponentType
from app.prediction.routing.builtin import DeviationOperator, ZScoreAnomalyOperator, spec_for
from app.prediction.routing.operator import OperatorInput, SignalSampling, role
from app.prediction.routing.registry import OperatorRegistry, OperatorSpecError, validate_spec
from app.prediction.routing.router import Router, default_registry
from app.prediction.routing.templates import AnalysisTemplate
from app.prediction.schemas import FallbackBehavior, OperatorSpec, OutputKind

from ..baselines.conftest import db, factory  # noqa: F401
from ..equipment.conftest import series
from ..rules.conftest import after_reference, references

BS = ComponentType.BALL_SCREW


def sampling(sid: str, cid: str, v) -> dict[str, SignalSampling]:
    out = {}
    for s in series(sid):
        if s.component_id != cid:
            continue
        t, _ = s.between(v.window.start.timestamp(), v.window.end.timestamp())
        if len(t) > 1:
            d = np.diff(t)
            out[role(s.signal.signal_id)] = SignalSampling(float(np.median(d)), len(t), float(d.max()))
    return out


@pytest.fixture
def s04(db):  # noqa: F811
    ref = references(db, "S04")["M01-BS1"]
    vs = after_reference("S04", "M01-BS1")

    def make(i: int, **kw) -> OperatorInput:
        v = vs[i]
        return OperatorInput("M01-BS1", BS, kw.pop("vector", v), kw.pop("reference", ref),
                             kw.pop("sampling", sampling("S04", "M01-BS1", v)))  # fmt: skip

    return make, len(vs)


def test_builtin_specs_declare_every_l5_02_field():
    reg = default_registry()
    assert len(reg.specs()) == 8
    for s in reg.specs():
        assert s.input_signals and s.supported_regimes and s.sampling and s.eligibility
        assert s.feature_ref and s.model_version and s.timeout_s > 0 and s.fallback


@pytest.mark.parametrize(
    "change",
    [
        {"operator_id": "no-version"},
        {"input_signals": ["speed", "torque", "current"]},
        {"feature_ref": "ball_screw@9.9.9"},
        {"feature_ref": "vacuum_cup@1.0.0"},
    ],
)
def test_registry_rejects_inconsistent_specs(change):
    spec = spec_for("x", "1.0.0", BS, OutputKind.ANOMALY_SCORE).model_copy(update=change)
    with pytest.raises(OperatorSpecError):
        validate_spec(spec)


def test_incomplete_spec_and_unknown_condition_are_refused():
    base = spec_for("x", "1.0.0", BS, OutputKind.ANOMALY_SCORE).model_dump()
    with pytest.raises(ValueError):
        OperatorSpec.model_validate({**base, "eligibility": []})
    bad = {**base, "eligibility": [{"code": "TRUST_ME", "description": {"zh": "x", "en": "x"}}]}
    with pytest.raises(OperatorSpecError, match="unknown eligibility"):
        validate_spec(OperatorSpec.model_validate(bad))
    reg = OperatorRegistry()
    reg.register(DeviationOperator(BS))
    with pytest.raises(OperatorSpecError, match="already registered"):
        reg.register(DeviationOperator(BS))


def test_routes_by_component_type_with_typed_results(s04):
    make, n = s04
    results = Router().route(make(n - 1))  # late S04 window: drifted
    kinds = {r.operator_id: r.kind for r in results}
    assert kinds == {"deviation-ball_screw@1.0.0": "degradation_indicator",
                     "zscore-anomaly-ball_screw@1.0.0": "anomaly_score"}  # fmt: skip
    dev = results[0]
    assert dev.value > 8 and dev.higher_is_worse and dev.meta.is_simulated
    assert Router().route(make(0))[0].value < dev.value


def test_template_only_component_is_unsupported(s04):
    make, _ = s04
    x = make(0)
    cam = OperatorInput("A01-CAM1", ComponentType.CAM, x.vector)
    (r,) = Router().route(cam)
    assert r.kind == "unsupported" and r.reason == "COMPONENT_TEMPLATE_ONLY"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"reference": None}, "INELIGIBLE_INPUT"),
        ({"sampling": {}}, "INSUFFICIENT_DATA"),
        (
            {"sampling": {"speed": SignalSampling(60.0, 50), "torque": SignalSampling(60.0, 50)}},
            "DATA_QUALITY",
        ),
    ],
)
def test_ineligible_inputs_yield_unsupported_prediction(s04, change, reason):
    make, _ = s04
    results = Router().route(make(0, **change))
    assert [r.reason for r in results] == [reason, reason]


def test_mismatched_feature_version_is_ineligible(s04):
    make, _ = s04
    x = make(0)
    old = x.vector.model_copy(update={"feature_ref": "ball_screw@1.0.0"})
    assert {r.reason for r in Router().route(make(0, vector=old))} == {"INELIGIBLE_INPUT"}


class Slow:
    def __init__(self, version: str, fallback: FallbackBehavior, delay: float = 1.0):
        self.spec = spec_for("slow", version, BS, OutputKind.DEGRADATION_INDICATOR, timeout_s=0.1,
                             fallback=fallback)  # fmt: skip
        self.inner, self.delay = DeviationOperator(BS), delay

    def run(self, x):
        time.sleep(self.delay)
        return self.inner.run(x).model_copy(update={"operator_id": self.spec.operator_id})


class Broken(Slow):
    def run(self, x):
        raise RuntimeError("model file missing")


def _router(*ops, fallback_op=None):
    reg = default_registry()
    for op in ops:
        reg.register(op)
    tpl = AnalysisTemplate(BS, (ops[-1].spec.operator_id,), "deviation-ball_screw@1.0.0")
    return Router(reg, {BS: tpl})


def test_timeout_returns_unsupported_when_declared(s04):
    make, _ = s04
    t = time.perf_counter()
    (r,) = _router(Slow("2.0.0", FallbackBehavior.RETURN_UNSUPPORTED)).route(make(0))
    assert r.kind == "unsupported" and r.reason == "TIMEOUT" and time.perf_counter() - t < 0.8


def test_timeout_falls_back_to_the_statistical_baseline(s04):
    make, _ = s04
    (r,) = _router(Slow("2.0.0", FallbackBehavior.USE_STATISTICAL_BASELINE)).route(make(0))
    assert r.kind == "degradation_indicator" and r.operator_id == "deviation-ball_screw@1.0.0"


def test_timeout_falls_back_to_the_previous_version(s04):
    make, _ = s04
    old = Slow("1.0.0", FallbackBehavior.RETURN_UNSUPPORTED, delay=0.0)
    new = Slow("2.0.0", FallbackBehavior.USE_PREVIOUS_VERSION)
    (r,) = _router(old, new).route(make(0))
    assert r.kind == "degradation_indicator" and r.operator_id == "slow-ball_screw@1.0.0"


def test_previous_version_missing_reports_the_timeout(s04):
    make, _ = s04
    (r,) = _router(Slow("2.0.0", FallbackBehavior.USE_PREVIOUS_VERSION)).route(make(0))
    assert r.reason == "TIMEOUT"


def test_a_crashing_model_is_unavailable_not_fatal(s04):
    make, _ = s04
    (r,) = _router(Broken("2.0.0", FallbackBehavior.RETURN_UNSUPPORTED)).route(make(0))
    assert r.reason == "MODEL_UNAVAILABLE"
    (r,) = _router(Broken("2.0.0", FallbackBehavior.USE_STATISTICAL_BASELINE)).route(make(0))
    assert r.kind == "degradation_indicator"


def test_anomaly_operator_is_not_a_probability(s04):
    make, n = s04
    r = ZScoreAnomalyOperator(BS).run(make(n - 1))
    assert r.kind == "anomaly_score" and r.score > 4 and not hasattr(r, "probability")
