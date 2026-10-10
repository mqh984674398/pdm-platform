"""Statistical operators that ship with the platform (deterministic, no training).

``deviation@1.0.0`` gives a degradation indicator: the robust deviation of the component type's main
health feature from the lifecycle's verified healthy reference (per regime where available). It is
also the operator behind the ``USE_STATISTICAL_BASELINE`` fallback. ``zscore-anomaly@1.0.0`` gives an
anomaly score: the largest absolute deviation over all features with reference statistics.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.schemas import LocalizedText, ResultMeta
from app.equipment.schemas import ComponentType
from app.monitoring.baselines.stats import deviation
from app.monitoring.features.definitions import FEATURE_SETS
from app.prediction.routing.operator import OperatorInput
from app.prediction.schemas import (
    AnomalyScoreResult,
    DegradationIndicatorResult,
    EligibilityCondition,
    FallbackBehavior,
    OperatorSpec,
    OutputKind,
    PredictionResult,
    SamplingRequirement,
    UnsupportedPrediction,
    UnsupportedReason,
)

C = ComponentType
# component type -> (signal roles with their max sampling interval s, main health feature, fallback)
PROFILES: dict[ComponentType, tuple[dict[str, float], list[str]]] = {
    C.BALL_SCREW: ({"speed": 10.0, "torque": 10.0}, ["torque_cruise_residual", "torque_cruise"]),
    C.LINEAR_MOTOR: ({"speed": 10.0}, ["speed_ripple"]),
    C.PNEUMATIC_CYLINDER: (
        {"extend_time": 120.0, "retract_time": 120.0},
        ["extend_residual", "extend_median"],
    ),
    C.VACUUM_CUP: ({"release_time": 120.0}, ["release_residual", "release_median"]),
}
MIN_SAMPLES = 10


def _cond(code: str, zh: str, en: str) -> EligibilityCondition:
    return EligibilityCondition(code=code, description=LocalizedText(zh=zh, en=en))


ELIGIBILITY = [
    _cond("FEATURE_SET_MATCH", "特征版本与模型一致", "Feature version matches the model"),
    _cond("FEATURES_PRESENT", "窗口中有可用特征", "The window has usable features"),
    _cond("SAMPLING_OK", "采样满足要求", "Sampling meets the requirements"),
    _cond("VERIFIED_REFERENCE", "当前安装有已确认的健康参考", "The installation has a verified reference"),
]


def spec_for(
    name: str,
    version: str,
    ctype: ComponentType,
    kind: OutputKind,
    timeout_s: float = 5.0,
    fallback: FallbackBehavior = FallbackBehavior.RETURN_UNSUPPORTED,
) -> OperatorSpec:
    roles, _ = PROFILES[ctype]
    fs = FEATURE_SETS[ctype]
    return OperatorSpec(
        operator_id=f"{name}-{ctype.value.lower()}@{version}",
        component_types=[ctype],
        input_signals=sorted(roles),
        supported_regimes=["*"],
        sampling=[
            SamplingRequirement(signal_id=r, max_interval_s=i, min_samples=MIN_SAMPLES)
            for r, i in roles.items()
        ],
        feature_ref=f"{fs.feature_set}@{fs.version}",
        output_kind=kind,
        model_version=f"{name}@{version}",
        timeout_s=timeout_s,
        fallback=fallback,
        eligibility=ELIGIBILITY,
    )


def meta(spec: OperatorSpec, x: OperatorInput) -> ResultMeta:
    return ResultMeta(
        model_version=spec.model_version,
        feature_version=x.vector.feature_ref,
        config_version=x.reference.baseline_id if x.reference else "no-reference",
        computed_at=datetime.now(UTC),
        data_window=x.vector.window,
        is_simulated=x.vector.is_simulated,
    )


def unsupported(
    spec: OperatorSpec,
    x: OperatorInput,
    reason: UnsupportedReason,
    detail: LocalizedText,
    operator_id: str | None = None,
) -> UnsupportedPrediction:
    return UnsupportedPrediction(
        operator_id=operator_id or spec.operator_id,
        component_id=x.component_id,
        lifecycle_id=x.lifecycle_id,
        regime_id=x.regime_id,
        meta=meta(spec, x),
        requested_kind=spec.output_kind,
        reason=reason,
        detail=detail,
    )


def _stats(x: OperatorInput, feature: str):
    ref = x.reference
    if ref is None:
        return None
    return ref.regime_stats.get(x.regime_id or "", {}).get(feature) or ref.stats.get(feature)


class DeviationOperator:
    def __init__(self, ctype: ComponentType, version: str = "1.0.0", **kw):
        self.ctype = ctype
        self.spec = spec_for("deviation", version, ctype, OutputKind.DEGRADATION_INDICATOR, **kw)

    def run(self, x: OperatorInput) -> PredictionResult:
        for f in PROFILES[self.ctype][1]:
            value, st = x.vector.values.get(f), _stats(x, f)
            if value is not None and st is not None:
                return DegradationIndicatorResult(
                    operator_id=self.spec.operator_id,
                    component_id=x.component_id,
                    lifecycle_id=x.lifecycle_id,
                    regime_id=x.regime_id,
                    meta=meta(self.spec, x),
                    value=deviation(value, st),
                    unit=f"robust deviation of {f}",
                    reference_baseline_id=x.reference.baseline_id,
                    higher_is_worse=True,
                )
        return unsupported(
            self.spec,
            x,
            UnsupportedReason.INSUFFICIENT_DATA,
            LocalizedText(
                zh="主要健康特征在本窗口不可用", en="The main health feature is unavailable in this window"
            ),
        )


class ZScoreAnomalyOperator:
    def __init__(self, ctype: ComponentType, version: str = "1.0.0", **kw):
        self.ctype = ctype
        self.spec = spec_for("zscore-anomaly", version, ctype, OutputKind.ANOMALY_SCORE, **kw)

    def run(self, x: OperatorInput) -> PredictionResult:
        zs = [
            abs(deviation(v, st))
            for f, v in x.vector.values.items()
            if v is not None and (st := _stats(x, f))
        ]
        if not zs:
            return unsupported(
                self.spec,
                x,
                UnsupportedReason.INSUFFICIENT_DATA,
                LocalizedText(
                    zh="没有可与参考比较的特征", en="No feature can be compared with the reference"
                ),
            )
        return AnomalyScoreResult(
            operator_id=self.spec.operator_id,
            component_id=x.component_id,
            lifecycle_id=x.lifecycle_id,
            regime_id=x.regime_id,
            meta=meta(self.spec, x),
            score=max(zs),
            threshold=4.0,
            scale="max robust deviation from the verified reference",
        )


def builtin_operators() -> list:
    return [cls(t) for t in PROFILES for cls in (DeviationOperator, ZScoreAnomalyOperator)]
