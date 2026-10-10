"""Contract schema tests for T003."""

import re
import typing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from app.api.contracts import CONTRACT_MODELS
from app.core.schemas import ResultMeta, TimeWindow
from app.decision.schemas import HealthState
from app.equipment.schemas import (
    ComponentLifecycle,
    LifecycleStatus,
    MaintenanceEvent,
    MaintenanceEventType,
    MaintenanceWorkflowState,
    OperatingState,
    can_transition,
)
from app.monitoring.schemas import Baseline, BaselineKind
from app.prediction import schemas as pred

REQUIREMENTS = (Path(__file__).resolve().parents[2] / "REQUIREMENTS.md").read_text(encoding="utf-8")
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _requirement(rid: str) -> str:
    line = re.search(rf"^\| {rid} \| (.+) \|$", REQUIREMENTS, re.M)
    assert line, rid
    return line.group(1)


def _enum_tokens(text: str) -> list[str]:
    return re.findall(r"\b[A-Z][A-Z_]{2,}\b", text)


def meta(**kw) -> ResultMeta:
    base = dict(
        model_version="m@1",
        feature_version="f@1",
        config_version="c@1",
        computed_at=T0 + timedelta(days=1),
        data_window=TimeWindow(start=T0, end=T0 + timedelta(days=1)),
        is_simulated=True,
    )
    return ResultMeta(**(base | kw))


RESULT_BASE = dict(operator_id="op", component_id="c1", lifecycle_id="l1", regime_id=None)


# --- enums match REQUIREMENTS exactly -------------------------------------------------------


@pytest.mark.parametrize(
    ("enum", "rid"),
    [(OperatingState, "L3-02"), (HealthState, "L6-04"), (MaintenanceWorkflowState, "L3-07")],
)
def test_enum_values_match_requirements(enum, rid):
    expected = list(
        dict.fromkeys(t for t in _enum_tokens(_requirement(rid)) if t not in {"MUST", "NOT", "OR"})
    )
    assert [e.value for e in enum] == expected


def test_baseline_kinds_cover_three_independent_baselines():
    assert {k.value for k in BaselineKind} == {"VERIFIED_HEALTHY", "ADAPTIVE", "DEGRADATION_HISTORY"}


# --- provenance on every result -------------------------------------------------------------


RESULT_MODELS = [
    pred.AnomalyScoreResult,
    pred.ClassProbabilityResult,
    pred.DegradationIndicatorResult,
    pred.FailureProbabilityResult,
    pred.UnsupportedPrediction,
]


def test_every_result_schema_carries_result_meta():
    from app.decision.schemas import Decision, Evidence

    for model in [*RESULT_MODELS, Baseline, Evidence, Decision]:
        field = model.model_fields["meta"]
        assert field.annotation is ResultMeta and field.is_required(), model.__name__
    assert set(ResultMeta.model_fields) == {
        "model_version",
        "feature_version",
        "config_version",
        "computed_at",
        "data_window",
        "is_simulated",
    }


def test_simulated_flag_is_required_wherever_data_is_carried():
    with_flag = [m for m in CONTRACT_MODELS if "is_simulated" in m.model_fields]
    assert len(with_flag) >= 8
    for m in with_flag:
        assert m.model_fields["is_simulated"].is_required(), m.__name__


def test_naive_timestamps_rejected():
    with pytest.raises(ValidationError):
        TimeWindow(start=datetime(2026, 1, 1), end=datetime(2026, 1, 2))


def test_time_window_must_be_ordered():
    with pytest.raises(ValidationError):
        TimeWindow(start=T0, end=T0)


# --- typed prediction results ---------------------------------------------------------------


ADAPTER = TypeAdapter(pred.PredictionResult)


def test_union_discriminates_by_kind():
    payload = {"kind": "anomaly_score", "score": 3.2, "threshold": 3.0, "scale": "z-score", **RESULT_BASE}
    payload["meta"] = meta().model_dump(mode="json")
    assert isinstance(ADAPTER.validate_python(payload), pred.AnomalyScoreResult)


def test_kinds_are_not_interchangeable():
    # An anomaly score payload cannot be read as a failure probability.
    payload = {"kind": "failure_probability", "score": 0.9, "scale": "0..1", **RESULT_BASE}
    payload["meta"] = meta().model_dump(mode="json")
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(payload)


def test_union_accepts_unsupported_prediction():
    r = pred.UnsupportedPrediction(
        **RESULT_BASE,
        meta=meta(),
        requested_kind=pred.OutputKind.FAILURE_PROBABILITY,
        reason=pred.UnsupportedReason.NO_FAILURE_EVIDENCE,
        detail={"zh": "缺少失效证据", "en": "No failure evidence"},
    )
    assert ADAPTER.validate_python(r.model_dump()) == r


def test_union_members_cover_every_output_kind_plus_unsupported():
    members = typing.get_args(typing.get_args(pred.PredictionResult)[0])
    kinds = {m.model_fields["kind"].default for m in members}
    assert kinds == {k.value for k in pred.OutputKind} | {"unsupported"}


def test_failure_probability_requires_failure_evidence():
    with pytest.raises(ValidationError):
        pred.FailureProbabilityResult(
            **RESULT_BASE,
            meta=meta(),
            probability=0.2,
            horizon_hours=24,
            failure_events_in_training=0,
            censoring_method="kaplan-meier",
        )


def test_class_probabilities_must_form_distribution():
    with pytest.raises(ValidationError):
        pred.ClassProbabilityResult(
            **RESULT_BASE, meta=meta(), probabilities={"ok": 0.7, "worn": 0.7}, calibrated=False
        )
    ok = pred.ClassProbabilityResult(
        **RESULT_BASE, meta=meta(), probabilities={"ok": 0.7, "worn": 0.3}, calibrated=True
    )
    assert ok.probabilities["worn"] == 0.3


def test_operator_spec_declares_all_l5_02_fields():
    required = {n for n, f in pred.OperatorSpec.model_fields.items() if f.is_required()}
    assert {
        "input_signals",
        "supported_regimes",
        "sampling",
        "feature_ref",
        "output_kind",
        "model_version",
        "timeout_s",
        "fallback",
        "eligibility",
    } <= required


# --- lifecycle, maintenance, baselines ------------------------------------------------------


def test_replacement_event_requires_new_lifecycle():
    common = dict(
        event_id="e1",
        component_id="c1",
        lifecycle_id="l1",
        performed_at=T0,
        performed_by="u",
        is_simulated=True,
    )
    with pytest.raises(ValidationError):
        MaintenanceEvent(**common, type=MaintenanceEventType.REPLACEMENT)
    with pytest.raises(ValidationError):
        MaintenanceEvent(**common, type=MaintenanceEventType.LUBRICATION, new_lifecycle_id="l2")
    assert MaintenanceEvent(**common, type=MaintenanceEventType.REPLACEMENT, new_lifecycle_id="l2")


def test_retired_lifecycle_consistency():
    with pytest.raises(ValidationError):
        ComponentLifecycle(
            lifecycle_id="l1", component_id="c1", installed_at=T0, status=LifecycleStatus.RETIRED
        )


def test_workflow_transitions_follow_l3_07():
    W = MaintenanceWorkflowState
    path = [W.MAINTENANCE_EVENT, W.STABILIZATION, W.POST_MAINTENANCE_VALIDATION, W.NORMAL_MONITORING]
    assert all(can_transition(a, b) for a, b in zip(path, path[1:], strict=False))
    assert can_transition(W.POST_MAINTENANCE_VALIDATION, W.REVIEW_REQUIRED)
    assert not can_transition(W.MAINTENANCE_EVENT, W.NORMAL_MONITORING)  # stabilization cannot be skipped
    assert not can_transition(W.STABILIZATION, W.NORMAL_MONITORING)


def _baseline(kind, **kw):
    return Baseline(
        baseline_id="b1",
        kind=kind,
        component_id="c1",
        lifecycle_id="l1",
        regime_id=None,
        feature_ref="torque@1",
        window=TimeWindow(start=T0, end=T0 + timedelta(days=7)),
        stats={},
        meta=meta(),
        **kw,
    )


def test_verified_healthy_baseline_requires_explicit_verification():
    with pytest.raises(ValidationError):
        _baseline(BaselineKind.VERIFIED_HEALTHY)
    assert _baseline(BaselineKind.VERIFIED_HEALTHY, verified_by="eng1", verified_at=T0)
    with pytest.raises(ValidationError):
        _baseline(BaselineKind.ADAPTIVE, verified_by="eng1", verified_at=T0)


def test_contract_models_reject_unknown_fields():
    for m in CONTRACT_MODELS:
        assert m.model_config.get("extra") == "forbid", m.__name__
        assert issubclass(m, BaseModel)
