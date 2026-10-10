"""What an operator receives and must provide.

An operator is any model or statistical analysis that turns one component's evidence into a typed
prediction result (L5-06). It declares everything the router needs in its ``OperatorSpec`` (L5-02):
signal roles it reads, supported regimes, sampling requirements, feature schema, output kind, model
version, timeout and fallback, and the eligibility conditions checked before its output is used.

``input_signals`` and ``sampling[].signal_id`` name signal *roles* (the part after the component id,
e.g. ``torque`` in ``A02-BS1.torque``) so one spec serves every instance of a component type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.equipment.schemas import ComponentType
from app.monitoring.schemas import Baseline, FeatureVector
from app.prediction.schemas import OperatorSpec, PredictionResult


@dataclass(frozen=True)
class SignalSampling:
    """Observed sampling of one signal role in the window being analysed."""

    interval_s: float
    samples: int
    max_gap_s: float | None = None


@dataclass(frozen=True)
class OperatorInput:
    component_id: str
    component_type: ComponentType
    vector: FeatureVector
    reference: Baseline | None = None
    sampling: dict[str, SignalSampling] = field(default_factory=dict)

    @property
    def lifecycle_id(self) -> str:
        return self.vector.lifecycle_id

    @property
    def regime_id(self) -> str | None:
        return self.vector.regime_id


def role(signal_id: str) -> str:
    return signal_id.rsplit(".", 1)[-1]


class Operator(Protocol):
    spec: OperatorSpec

    def run(self, inputs: OperatorInput) -> PredictionResult: ...
