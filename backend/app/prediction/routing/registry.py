"""Operator registry: refuses incomplete or inconsistent specs (T021 AC1, L5-02).

Pydantic already requires every L5-02 field. The registry adds the checks a schema cannot express:
every input signal has a sampling requirement and vice versa, the feature schema exists and belongs
to the declared component types, every eligibility code is a known check, and ids are unique.
Operators are versioned as ``family@version``; the previous version of a family serves the
``USE_PREVIOUS_VERSION`` fallback.
"""

from __future__ import annotations

from app.monitoring.features.definitions import FEATURE_SETS
from app.prediction.routing.eligibility import CHECKS
from app.prediction.routing.operator import Operator
from app.prediction.schemas import OperatorSpec


class OperatorSpecError(ValueError):
    pass


def family(operator_id: str) -> tuple[str, tuple[int, ...]]:
    name, _, version = operator_id.partition("@")
    return name, tuple(int(p) for p in version.split(".")) if version else ()


def validate_spec(spec: OperatorSpec) -> None:
    problems = []
    if "@" not in spec.operator_id:
        problems.append("operator_id must be 'family@version'")
    signals, sampled = set(spec.input_signals), {s.signal_id for s in spec.sampling}
    if signals != sampled:
        problems.append(
            f"sampling requirements must cover exactly the input signals ({sorted(signals ^ sampled)})"
        )
    schemas = {f"{fs.feature_set}@{fs.version}": t for t, fs in FEATURE_SETS.items()}
    owner = schemas.get(spec.feature_ref)
    if owner is None:
        problems.append(f"unknown feature schema {spec.feature_ref}")
    elif any(t != owner for t in spec.component_types):
        problems.append(f"feature schema {spec.feature_ref} belongs to {owner.value} only")
    unknown = [c.code for c in spec.eligibility if c.code not in CHECKS]
    if unknown:
        problems.append(f"unknown eligibility conditions {unknown}")
    if not spec.model_version.strip():
        problems.append("model_version is empty")
    if problems:
        raise OperatorSpecError(f"{spec.operator_id}: " + "; ".join(problems))


class OperatorRegistry:
    def __init__(self) -> None:
        self._ops: dict[str, Operator] = {}

    def register(self, op: Operator) -> None:
        validate_spec(op.spec)
        if op.spec.operator_id in self._ops:
            raise OperatorSpecError(f"{op.spec.operator_id} is already registered")
        self._ops[op.spec.operator_id] = op

    def get(self, operator_id: str) -> Operator | None:
        return self._ops.get(operator_id)

    def specs(self) -> list[OperatorSpec]:
        return [o.spec for o in self._ops.values()]

    def previous(self, operator_id: str) -> Operator | None:
        name, version = family(operator_id)
        older = [
            (family(k)[1], o) for k, o in self._ops.items() if family(k)[0] == name and family(k)[1] < version
        ]
        return max(older, key=lambda x: x[0])[1] if older else None
