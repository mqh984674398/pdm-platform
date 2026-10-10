"""Route a component's window to the operators of its template (T021 AC2/AC3).

For each operator: eligibility is checked first (ineligible -> UnsupportedPrediction with the
reason); then it runs with its declared timeout. A timeout or a crash applies the declared fallback:
RETURN_UNSUPPORTED (TIMEOUT / MODEL_UNAVAILABLE), USE_PREVIOUS_VERSION (the previous registered
version of the same family, itself eligibility-checked), or USE_STATISTICAL_BASELINE (the template's
statistical operator). A fallback result keeps the fallback operator's id, so the source is visible.
A timed-out call cannot be killed in-process; its late result is discarded.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import UTC, datetime

from app.core.schemas import LocalizedText, ResultMeta
from app.prediction.routing import eligibility
from app.prediction.routing.builtin import builtin_operators, unsupported
from app.prediction.routing.operator import Operator, OperatorInput
from app.prediction.routing.registry import OperatorRegistry
from app.prediction.routing.templates import DEFAULT_TEMPLATES, AnalysisTemplate
from app.prediction.schemas import (
    FallbackBehavior,
    OperatorSpec,
    OutputKind,
    PredictionResult,
    UnsupportedPrediction,
    UnsupportedReason,
)

R = UnsupportedReason


def _t(zh: str, en: str) -> LocalizedText:
    return LocalizedText(zh=zh, en=en)


def default_registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    for op in builtin_operators():
        reg.register(op)
    return reg


class Router:
    def __init__(
        self, registry: OperatorRegistry | None = None, templates: dict | None = None, workers: int = 4
    ):
        self.registry = registry or default_registry()
        self.templates: dict = templates or DEFAULT_TEMPLATES
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="operator")

    def _invoke(self, op: Operator, x: OperatorInput) -> tuple[PredictionResult | None, R | None]:
        failure = eligibility.check(op.spec, x)
        if failure:
            return unsupported(op.spec, x, *failure), None
        future = self.pool.submit(op.run, x)
        try:
            return future.result(timeout=op.spec.timeout_s), None
        except FutureTimeout:
            future.cancel()
            return None, R.TIMEOUT
        except Exception:  # noqa: BLE001  (a broken model must not break routing)
            return None, R.MODEL_UNAVAILABLE

    def _fallback(self, op: Operator, tpl: AnalysisTemplate, x: OperatorInput, why: R) -> PredictionResult:
        spec: OperatorSpec = op.spec
        alt = None
        if spec.fallback == FallbackBehavior.USE_PREVIOUS_VERSION:
            alt = self.registry.previous(spec.operator_id)
        elif spec.fallback == FallbackBehavior.USE_STATISTICAL_BASELINE and tpl.statistical_fallback:
            alt = self.registry.get(tpl.statistical_fallback)
            alt = None if alt is op else alt
        if alt is not None:
            result, err = self._invoke(alt, x)
            if result is not None:
                return result
            why = err or why
        text = {
            R.TIMEOUT: _t(
                f"模型超过 {spec.timeout_s:g} 秒未返回",
                f"The model did not answer within {spec.timeout_s:g} s",
            ),
            R.MODEL_UNAVAILABLE: _t("模型运行失败", "The model failed to run"),
        }[why]
        return unsupported(spec, x, why, text)

    def route(self, x: OperatorInput) -> list[PredictionResult]:
        tpl = self.templates.get(x.component_type)
        if tpl is None or not tpl.operator_ids:
            return [self._template_only(x)]
        out: list[PredictionResult] = []
        for oid in tpl.operator_ids:
            op = self.registry.get(oid)
            if op is None:
                continue
            result, err = self._invoke(op, x)
            out.append(result if result is not None else self._fallback(op, tpl, x, err))
        return out

    @staticmethod
    def _template_only(x: OperatorInput) -> PredictionResult:
        return UnsupportedPrediction(
            operator_id="none",
            component_id=x.component_id,
            lifecycle_id=x.lifecycle_id,
            regime_id=x.regime_id,
            meta=ResultMeta(
                model_version="routing@1.0.0",
                feature_version=x.vector.feature_ref,
                config_version="templates@1.0.0",
                computed_at=datetime.now(UTC),
                data_window=x.vector.window,
                is_simulated=x.vector.is_simulated,
            ),
            requested_kind=OutputKind.DEGRADATION_INDICATOR,
            reason=R.COMPONENT_TEMPLATE_ONLY,
            detail=_t(
                "该部件类型只有模板，暂无可用模型", "This component type is a template without any model yet"
            ),
        )
