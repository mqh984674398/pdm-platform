"""L5 contracts: operator specifications and typed prediction results.

Result kinds keep their meaning (L5-06): an anomaly score is not a probability, a degradation
indicator is not a failure probability. Every place that accepts a prediction also accepts
``UnsupportedPrediction`` (GEN-07).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.core.schemas import ContractModel, LocalizedText, ResultMeta
from app.equipment.schemas import ComponentType


class OutputKind(StrEnum):
    ANOMALY_SCORE = "anomaly_score"
    CLASS_PROBABILITY = "class_probability"
    DEGRADATION_INDICATOR = "degradation_indicator"
    FAILURE_PROBABILITY = "failure_probability"


class SamplingRequirement(ContractModel):
    signal_id: str
    max_interval_s: float = Field(gt=0)
    min_samples: int = Field(gt=0)
    max_gap_s: float | None = Field(default=None, gt=0)


class EligibilityCondition(ContractModel):
    """A declarative precondition checked before the operator's output may be used (L6-01)."""

    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    description: LocalizedText


class FallbackBehavior(StrEnum):
    RETURN_UNSUPPORTED = "RETURN_UNSUPPORTED"
    USE_PREVIOUS_VERSION = "USE_PREVIOUS_VERSION"
    USE_STATISTICAL_BASELINE = "USE_STATISTICAL_BASELINE"


class OperatorSpec(ContractModel):
    """Declaration every model/operator must provide (L5-02)."""

    operator_id: str
    component_types: list[ComponentType] = Field(min_length=1)
    input_signals: list[str] = Field(min_length=1)
    supported_regimes: list[str] = Field(min_length=1, description="Regime ids, or ['*'] for regime-agnostic")
    sampling: list[SamplingRequirement] = Field(min_length=1)
    feature_ref: str = Field(description="feature_set@version")
    output_kind: OutputKind
    model_version: str
    timeout_s: float = Field(gt=0, le=600)
    fallback: FallbackBehavior
    eligibility: list[EligibilityCondition] = Field(min_length=1)


class _ResultBase(ContractModel):
    operator_id: str
    component_id: str
    lifecycle_id: str
    regime_id: str | None
    meta: ResultMeta


class AnomalyScoreResult(_ResultBase):
    kind: Literal["anomaly_score"] = "anomaly_score"
    score: float
    threshold: float | None = None
    scale: str = Field(description="How to read the score, e.g. 'z-score', 'isolation-forest 0..1'")


class ClassProbabilityResult(_ResultBase):
    kind: Literal["class_probability"] = "class_probability"
    probabilities: dict[str, float] = Field(min_length=2)
    calibrated: bool

    @model_validator(mode="after")
    def _distribution(self) -> ClassProbabilityResult:
        values = self.probabilities.values()
        if any(p < 0 or p > 1 for p in values) or abs(sum(values) - 1.0) > 1e-6:
            raise ValueError("probabilities must be in [0, 1] and sum to 1")
        return self


class DegradationIndicatorResult(_ResultBase):
    kind: Literal["degradation_indicator"] = "degradation_indicator"
    value: float
    unit: str
    reference_baseline_id: str
    higher_is_worse: bool


class FailureProbabilityResult(_ResultBase):
    """Only valid when genuine failure/lifecycle evidence exists (L5-05)."""

    kind: Literal["failure_probability"] = "failure_probability"
    probability: float = Field(ge=0, le=1)
    horizon_hours: float = Field(gt=0)
    failure_events_in_training: int = Field(gt=0)
    censoring_method: str = Field(min_length=1)


class UnsupportedReason(StrEnum):
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    DATA_QUALITY = "DATA_QUALITY"
    UNSUPPORTED_REGIME = "UNSUPPORTED_REGIME"
    INELIGIBLE_INPUT = "INELIGIBLE_INPUT"
    TIMEOUT = "TIMEOUT"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    NO_FAILURE_EVIDENCE = "NO_FAILURE_EVIDENCE"
    COMPONENT_TEMPLATE_ONLY = "COMPONENT_TEMPLATE_ONLY"


class UnsupportedPrediction(_ResultBase):
    kind: Literal["unsupported"] = "unsupported"
    requested_kind: OutputKind
    reason: UnsupportedReason
    detail: LocalizedText


PredictionResult = Annotated[
    AnomalyScoreResult
    | ClassProbabilityResult
    | DegradationIndicatorResult
    | FailureProbabilityResult
    | UnsupportedPrediction,
    Field(discriminator="kind"),
]
