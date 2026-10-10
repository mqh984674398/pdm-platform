"""Component analysis templates: which operators analyse which component type (L5-01).

Operators in a template are independent analyses, not a pipeline; each one's result is routed and
checked on its own. A type without telemetry (cam, gear) has a template with no operators and every
request for it is answered with COMPONENT_TEMPLATE_ONLY.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.equipment.schemas import ComponentType


@dataclass(frozen=True)
class AnalysisTemplate:
    component_type: ComponentType
    operator_ids: tuple[str, ...]
    statistical_fallback: str | None  # operator behind USE_STATISTICAL_BASELINE


def _builtin(t: ComponentType) -> AnalysisTemplate:
    k = t.value.lower()
    return AnalysisTemplate(t, (f"deviation-{k}@1.0.0", f"zscore-anomaly-{k}@1.0.0"), f"deviation-{k}@1.0.0")


C = ComponentType
DEFAULT_TEMPLATES: dict[ComponentType, AnalysisTemplate] = {
    **{t: _builtin(t) for t in (C.BALL_SCREW, C.LINEAR_MOTOR, C.PNEUMATIC_CYLINDER, C.VACUUM_CUP)},
    C.CAM: AnalysisTemplate(C.CAM, (), None),
    C.GEAR: AnalysisTemplate(C.GEAR, (), None),
}
