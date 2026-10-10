"""A registered model as a routable operator (T021 interface) giving class probabilities.

The probabilities are the model's uncalibrated class scores (``calibrated=False``); they are not a
failure probability (L5-06). Fallback on timeout or failure: the statistical deviation operator.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.prediction.models.registry import ModelRecord
from app.prediction.models.train import degraded_probability
from app.prediction.routing.builtin import ELIGIBILITY, MIN_SAMPLES, PROFILES, meta
from app.prediction.routing.operator import OperatorInput
from app.prediction.schemas import (
    ClassProbabilityResult,
    FallbackBehavior,
    OperatorSpec,
    OutputKind,
    PredictionResult,
    SamplingRequirement,
)


class TrainedModelOperator:
    def __init__(self, model: Any, record: ModelRecord, timeout_s: float = 2.0):
        self.model, self.record = model, record
        roles, _ = PROFILES[record.component_type]
        self.spec = OperatorSpec(
            operator_id=record.model_id,
            component_types=[record.component_type],
            input_signals=sorted(roles),
            supported_regimes=["*"],
            sampling=[
                SamplingRequirement(signal_id=r, max_interval_s=i, min_samples=MIN_SAMPLES)
                for r, i in roles.items()
            ],
            feature_ref=record.feature_ref,
            output_kind=OutputKind.CLASS_PROBABILITY,
            model_version=f"{record.model_id} ({record.kind}, SIMULATED training)",
            timeout_s=timeout_s,
            fallback=FallbackBehavior.USE_STATISTICAL_BASELINE,
            eligibility=[c for c in ELIGIBILITY if c.code != "VERIFIED_REFERENCE"],
        )

    def run(self, x: OperatorInput) -> PredictionResult:
        row = np.array(
            [
                [
                    x.vector.values.get(f) if x.vector.values.get(f) is not None else np.nan
                    for f in self.record.features
                ]
            ],
            dtype=float,
        )
        p = float(degraded_probability(self.model, row)[0])
        return ClassProbabilityResult(
            operator_id=self.spec.operator_id,
            component_id=x.component_id,
            lifecycle_id=x.lifecycle_id,
            regime_id=x.regime_id,
            meta=meta(self.spec, x),
            probabilities={"healthy": 1.0 - p, "degraded": p},
            calibrated=False,
        )
