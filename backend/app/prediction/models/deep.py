# ruff: noqa: E501, B905
"""Interface for deep sequence models such as LSTM and D-RCNN (D-046).

The platform defines how such a model is described, trained, fine-tuned, optimised, stored and routed;
the model code itself is supplied by an adapter. Nothing here trains or ships a model, and no deep
learning framework is bundled: the built-in LSTM and D-RCNN adapters report themselves unavailable until
an adapter with a real backend is registered. An adapter implements ``DeepModelAdapter``:

- ``contract``: what the model reads (a sequence of feature windows, or a raw waveform), the sequence
  length, the minimum sampling rate and the minimum labelled data it needs;
- ``fit``: train from scratch, or fine-tune when a ``base`` model is passed;
- ``predict_degraded``: probability-like score per sample (never calibrated, never a failure probability);
- ``search_space``: parameter choices tried by ``tune``.

The same gates as the tree models apply: labels must be recorded truth (never health states or online
observations), windows of one installation never straddle the train/validation split, the validation
must reach ROC AUC 0.8, and the artifact is stored immutably with its hash in the model registry.
A model trained here still has to pass the deployment gate before it can decide anything.
"""

from __future__ import annotations

import itertools
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np
from pydantic import Field

from app.core.schemas import ContractModel, LocalizedText
from app.equipment.schemas import ComponentType
from app.prediction.models.registry import ModelRecord, ModelRegistry, stamp
from app.prediction.models.train import metrics
from app.prediction.routing.builtin import ELIGIBILITY, meta, unsupported
from app.prediction.routing.operator import OperatorInput
from app.prediction.schemas import (
    ClassProbabilityResult,
    FallbackBehavior,
    OperatorSpec,
    OutputKind,
    PredictionResult,
    SamplingRequirement,
    UnsupportedReason,
)

MIN_AUC = 0.8
TRUTH_PREFIXES = ("SIMULATED truth", "Recorded failure")  # same rule as the deployment gate


class DeepModelError(ValueError):
    pass


class InputKind(StrEnum):
    WINDOW_SEQUENCE = "WINDOW_SEQUENCE"  # the last N feature windows of the installation
    WAVEFORM = "WAVEFORM"  # raw high-frequency samples of one window


class InputContract(ContractModel):
    kind: InputKind
    features: list[str] = Field(default_factory=list, description="Window sequence: feature names, in order")
    sequence_length: int = Field(default=1, gt=0, description="Window sequence: windows per sample")
    signal_role: str | None = Field(default=None, description="Waveform: signal role, e.g. vibration")
    min_sampling_hz: float | None = Field(default=None, gt=0, description="Waveform: lowest sampling rate")
    min_training_samples: int = Field(default=200, gt=0)
    min_fault_samples: int = Field(default=20, gt=0)


@dataclass(frozen=True)
class TrainingData:
    """``x``: (n, sequence_length, n_features) for window sequences, or (n, n_samples) for waveforms."""

    x: np.ndarray
    y: np.ndarray  # 1 = degraded per recorded truth
    groups: list[str]  # scenario/lifecycle of each sample
    label_definition: str
    scenarios: list[str]
    is_simulated: bool


class DeepModelAdapter(ABC):
    family: str
    component_types: tuple[ComponentType, ...]
    contract: InputContract

    @abstractmethod
    def available(self) -> str | None:
        """None when the backend can run; otherwise why it cannot."""

    @abstractmethod
    def fit(self, data: TrainingData, params: dict[str, Any], seed: int, base: Any | None = None) -> Any:
        """Train a new model, or fine-tune ``base`` when given."""

    @abstractmethod
    def predict_degraded(self, model: Any, x: np.ndarray) -> np.ndarray: ...

    def default_params(self) -> dict[str, Any]:
        return {}

    def search_space(self) -> dict[str, list[Any]]:
        return {}


class PlaceholderAdapter(DeepModelAdapter):
    """Declares the contract of a family whose backend is not installed. Never trains or predicts."""

    def available(self) -> str | None:
        return "no deep learning backend adapter is registered for this family"

    def fit(self, data, params, seed, base=None):
        raise DeepModelError(self.available())

    def predict_degraded(self, model, x):
        raise DeepModelError(self.available())


_BALL_TYPES = (ComponentType.BALL_SCREW, ComponentType.LINEAR_MOTOR, ComponentType.PNEUMATIC_CYLINDER,
               ComponentType.VACUUM_CUP)  # fmt: skip


class LstmPlaceholder(PlaceholderAdapter):
    family = "lstm"
    component_types = _BALL_TYPES
    contract = InputContract(kind=InputKind.WINDOW_SEQUENCE, sequence_length=24, min_training_samples=500,
                             min_fault_samples=50)  # fmt: skip


class DrcnnPlaceholder(PlaceholderAdapter):
    family = "drcnn"
    component_types = _BALL_TYPES
    contract = InputContract(kind=InputKind.WAVEFORM, signal_role="vibration", min_sampling_hz=1000.0,
                             min_training_samples=500, min_fault_samples=50)  # fmt: skip


ADAPTERS: dict[str, DeepModelAdapter] = {}


def register_adapter(adapter: DeepModelAdapter, replace: bool = False) -> None:
    """Add an adapter. A real backend for ``lstm`` or ``drcnn`` replaces the placeholder with ``replace``."""
    fam = getattr(adapter, "family", "")
    if not fam or not fam.replace("-", "").replace("_", "").isalnum() or fam != fam.lower():
        raise DeepModelError("adapter family must be a lower-case identifier")
    if fam in ADAPTERS and not replace and not isinstance(ADAPTERS[fam], PlaceholderAdapter):
        raise DeepModelError(f"adapter '{fam}' is already registered")
    c = adapter.contract
    if c.kind == InputKind.WINDOW_SEQUENCE and not (c.sequence_length >= 1):
        raise DeepModelError("a window-sequence adapter needs sequence_length")
    if c.kind == InputKind.WAVEFORM and not (c.signal_role and c.min_sampling_hz):
        raise DeepModelError("a waveform adapter needs signal_role and min_sampling_hz")
    ADAPTERS[fam] = adapter


def adapter_status() -> dict[str, str | None]:
    """family → None when usable, else the reason it is not."""
    return {f: a.available() for f, a in ADAPTERS.items()}


for _a in (LstmPlaceholder(), DrcnnPlaceholder()):
    register_adapter(_a)


# --- training, fine-tuning, optimisation ----------------------------------------------------------------


def _check(adapter: DeepModelAdapter, data: TrainingData) -> None:
    why = adapter.available()
    if why:
        raise DeepModelError(f"{adapter.family}: {why}")
    if not data.label_definition.startswith(TRUTH_PREFIXES):
        raise DeepModelError("labels must be recorded truth (simulated ground truth or documented failures)")
    for word in ("health", "adaptive", "online", "watch", "warning", "critical"):
        if word in data.label_definition.lower():
            raise DeepModelError(f"labels refer to '{word}'; only recorded truth may label training")
    c = adapter.contract
    if len(data.y) != len(data.x) or len(data.groups) != len(data.y):
        raise DeepModelError("x, y and groups must have the same length")
    if c.kind == InputKind.WINDOW_SEQUENCE and (
        data.x.ndim != 3 or data.x.shape[1] != c.sequence_length or data.x.shape[2] != len(c.features)
    ):
        raise DeepModelError(f"x must be (n, {c.sequence_length}, {len(c.features)}) for this adapter")
    if len(data.y) < c.min_training_samples or int(data.y.sum()) < c.min_fault_samples:
        raise DeepModelError(
            f"not enough labelled data: {len(data.y)} samples with {int(data.y.sum())} faults; "
            f"needs {c.min_training_samples} and {c.min_fault_samples}"
        )


def _split(data: TrainingData, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Hold out whole groups (installations): about a fifth of them, chosen with the seed."""
    groups = sorted(set(data.groups))
    if len(groups) < 3:
        raise DeepModelError("validation needs at least three installations (groups)")
    rng = random.Random(seed)
    held = set(rng.sample(groups, max(1, len(groups) // 5)))
    mask = np.array([g in held for g in data.groups])
    if len(set(data.y[mask].tolist())) < 2 or len(set(data.y[~mask].tolist())) < 2:
        raise DeepModelError("both splits need healthy and degraded samples; change the seed or add data")
    return ~mask, mask


def train_deep(
    registry: ModelRegistry,
    adapter: DeepModelAdapter,
    data: TrainingData,
    *,
    version: str,
    component_type: ComponentType,
    feature_ref: str,
    params: dict[str, Any] | None = None,
    seed: int = 0,
    base_model_id: str | None = None,
) -> ModelRecord:
    """Train (or fine-tune from ``base_model_id``), validate on held-out installations, store immutably."""
    _check(adapter, data)
    if component_type not in adapter.component_types:
        raise DeepModelError(f"{adapter.family} does not apply to {component_type.value}")
    base = None
    if base_model_id:
        base, base_rec = registry.load(base_model_id)
        if base_rec.kind != adapter.family or base_rec.component_type != component_type:
            raise DeepModelError("the base model must be the same family and component type")
    use = {**adapter.default_params(), **(params or {})}
    train, held = _split(data, seed)
    sub = TrainingData(data.x[train], data.y[train], [g for g, m in zip(data.groups, train) if m],
                       data.label_definition, data.scenarios, data.is_simulated)  # fmt: skip
    model = adapter.fit(sub, use, seed, base)
    p = np.asarray(adapter.predict_degraded(model, data.x[held]), dtype=float)
    m = metrics(data.y[held], p)
    if m["roc_auc"] is None or m["roc_auc"] < MIN_AUC:
        raise DeepModelError(f"validation ROC AUC {m['roc_auc']} is below {MIN_AUC}; the model is not stored")
    rec = ModelRecord(
        model_id=f"{adapter.family}@{version}",
        kind=adapter.family,
        component_type=component_type,
        feature_ref=feature_ref,
        features=adapter.contract.features or [adapter.contract.signal_role or "waveform"],
        label_definition=data.label_definition,
        training_scenarios=data.scenarios,
        params={
            **use,
            "fine_tuned_from": base_model_id,
            "contract": adapter.contract.model_dump(mode="json"),
        },
        seed=seed,
        metrics={"validation": m, "held_out_groups": sorted(set(g for g, k in zip(data.groups, held) if k))},
        is_simulated=data.is_simulated,
        created_at=stamp(),
    )
    return registry.save(model, rec)


def tune(
    adapter: DeepModelAdapter, data: TrainingData, *, trials: int = 8, seed: int = 0
) -> list[tuple[dict[str, Any], float]]:
    """Try parameter sets from the adapter's search space; best validation ROC AUC first. Stores nothing."""
    _check(adapter, data)
    space = adapter.search_space()
    if not space:
        raise DeepModelError("this adapter declares no search space")
    keys = sorted(space)
    combos = [dict(zip(keys, c)) for c in itertools.product(*(space[k] for k in keys))]
    random.Random(seed).shuffle(combos)
    train, held = _split(data, seed)
    sub = TrainingData(data.x[train], data.y[train], [g for g, m in zip(data.groups, train) if m],
                       data.label_definition, data.scenarios, data.is_simulated)  # fmt: skip
    out = []
    for params in combos[: max(1, trials)]:
        model = adapter.fit(sub, {**adapter.default_params(), **params}, seed, None)
        auc = metrics(data.y[held], np.asarray(adapter.predict_degraded(model, data.x[held]), dtype=float))[
            "roc_auc"
        ]
        out.append((params, -1.0 if auc is None else float(auc)))
    return sorted(out, key=lambda t: -t[1])


# --- routing -----------------------------------------------------------------------------------------


class DeepModelOperator:
    """A stored deep model as a routable operator. Without the input it needs it answers 'unsupported'."""

    def __init__(self, adapter: DeepModelAdapter, model: Any, record: ModelRecord, timeout_s: float = 5.0):
        self.adapter, self.model, self.record = adapter, model, record
        c = adapter.contract
        role = c.signal_role or "torque"
        self.spec = OperatorSpec(
            operator_id=record.model_id,
            component_types=[record.component_type],
            input_signals=[role],
            supported_regimes=["*"],
            sampling=[SamplingRequirement(signal_id=role, max_interval_s=1.0 / (c.min_sampling_hz or 0.1),
                                          min_samples=10)],
            feature_ref=record.feature_ref,
            output_kind=OutputKind.CLASS_PROBABILITY,
            model_version=f"{record.model_id} ({record.kind}{', SIMULATED training' if record.is_simulated else ''})",
            timeout_s=timeout_s,
            fallback=FallbackBehavior.USE_STATISTICAL_BASELINE,
            eligibility=[c for c in ELIGIBILITY if c.code != "VERIFIED_REFERENCE"],
        )  # fmt: skip

    def run(self, x: OperatorInput) -> PredictionResult:
        c = self.adapter.contract
        if c.kind == InputKind.WAVEFORM:
            if x.waveform is None:
                return unsupported(self.spec, x, UnsupportedReason.INSUFFICIENT_DATA, LocalizedText(
                    zh="没有提供原始高频波形", en="No raw high-frequency waveform was supplied"))  # fmt: skip
            row = np.asarray(x.waveform, dtype=float)[None, :]
        else:
            seq = [*x.history, x.vector][-c.sequence_length :]
            if len(seq) < c.sequence_length:
                return unsupported(self.spec, x, UnsupportedReason.INSUFFICIENT_DATA, LocalizedText(
                    zh=f"需要连续 {c.sequence_length} 个窗口，当前只有 {len(seq)} 个",
                    en=f"Needs {c.sequence_length} consecutive windows, only {len(seq)} available"))  # fmt: skip
            rows = [[v.values.get(f) for f in c.features] for v in seq]
            if any(val is None for r in rows for val in r):
                return unsupported(self.spec, x, UnsupportedReason.DATA_QUALITY, LocalizedText(
                    zh="序列中有窗口缺少所需特征", en="A window in the sequence lacks a required feature"))  # fmt: skip
            row = np.asarray([rows], dtype=float)
        pr = float(self.adapter.predict_degraded(self.model, row)[0])
        return ClassProbabilityResult(
            operator_id=self.spec.operator_id, component_id=x.component_id, lifecycle_id=x.lifecycle_id,
            regime_id=x.regime_id, meta=meta(self.spec, x),
            probabilities={"healthy": 1.0 - pr, "degraded": pr}, calibrated=False,
        )  # fmt: skip
