"""Eligibility conditions (L6-01): checked by the router before an operator runs.

Each code maps to one check. A spec may only name codes listed here; the registry refuses others, so
a declared condition can never be silently skipped.
"""

from __future__ import annotations

from collections.abc import Callable

from app.core.schemas import LocalizedText
from app.prediction.routing.operator import OperatorInput
from app.prediction.schemas import OperatorSpec, UnsupportedReason

Failure = tuple[UnsupportedReason, LocalizedText]
Check = Callable[[OperatorSpec, OperatorInput], Failure | None]


def _t(zh: str, en: str) -> LocalizedText:
    return LocalizedText(zh=zh, en=en)


def _feature_set(spec: OperatorSpec, x: OperatorInput) -> Failure | None:
    if x.vector.feature_ref != spec.feature_ref:
        return UnsupportedReason.INELIGIBLE_INPUT, _t(
            f"特征版本 {x.vector.feature_ref} 与模型要求的 {spec.feature_ref} 不一致",
            f"Feature version {x.vector.feature_ref} does not match the required {spec.feature_ref}",
        )
    return None


def _regime(spec: OperatorSpec, x: OperatorInput) -> Failure | None:
    if "*" in spec.supported_regimes:
        return None
    if x.regime_id is None or x.regime_id not in spec.supported_regimes:
        return UnsupportedReason.UNSUPPORTED_REGIME, _t(
            f"工况 {x.regime_id or '未知'} 不在模型支持范围内",
            f"Regime {x.regime_id or 'unknown'} is not supported by this model",
        )
    return None


def _sampling(spec: OperatorSpec, x: OperatorInput) -> Failure | None:
    for req in spec.sampling:
        got = x.sampling.get(req.signal_id)
        if got is None or got.samples < req.min_samples:
            return UnsupportedReason.INSUFFICIENT_DATA, _t(
                f"信号 {req.signal_id} 样本不足（需要至少 {req.min_samples} 个）",
                f"Signal {req.signal_id} has too few samples (needs at least {req.min_samples})",
            )
        too_sparse = got.interval_s > req.max_interval_s
        gap = req.max_gap_s is not None and (got.max_gap_s or 0.0) > req.max_gap_s
        if too_sparse or gap:
            return UnsupportedReason.DATA_QUALITY, _t(
                f"信号 {req.signal_id} 采样间隔或缺口超出要求",
                f"Signal {req.signal_id} sampling interval or gap exceeds the requirement",
            )
    return None


def _features(spec: OperatorSpec, x: OperatorInput) -> Failure | None:
    if not any(v is not None for v in x.vector.values.values()):
        return UnsupportedReason.INSUFFICIENT_DATA, _t(
            "该窗口没有可用特征", "No usable features in the window"
        )
    return None


def _reference(spec: OperatorSpec, x: OperatorInput) -> Failure | None:
    ref = x.reference
    if ref is None or ref.lifecycle_id != x.lifecycle_id or ref.feature_ref != spec.feature_ref:
        return UnsupportedReason.INELIGIBLE_INPUT, _t(
            "当前安装没有匹配的已确认健康参考", "No matching verified healthy reference for this installation"
        )
    return None


CHECKS: dict[str, Check] = {
    "FEATURE_SET_MATCH": _feature_set,
    "REGIME_SUPPORTED": _regime,
    "SAMPLING_OK": _sampling,
    "FEATURES_PRESENT": _features,
    "VERIFIED_REFERENCE": _reference,
}


def check(spec: OperatorSpec, x: OperatorInput) -> Failure | None:
    for cond in spec.eligibility:
        failure = CHECKS[cond.code](spec, x)
        if failure is not None:
            return failure
    return None
