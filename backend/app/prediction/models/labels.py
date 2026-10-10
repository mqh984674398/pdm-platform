"""Training labels from the simulator's ground truth (truth_components.csv), never from health states.

A window is ``degraded`` when the injected fault factor of its component reaches the threshold. Factors
include slow aging, so long aging scenarios cross the threshold late; this is the simulated truth's
definition, recorded with every model.
"""

from __future__ import annotations

from app.equipment.schemas import ComponentType

C = ComponentType
LABELS: dict[ComponentType, tuple[tuple[str, ...], float]] = {
    C.BALL_SCREW: (("friction_factor",), 1.15),
    C.LINEAR_MOTOR: (("ripple_fraction",), 0.02),
    C.PNEUMATIC_CYLINDER: (("extend_factor", "retract_factor"), 1.15),
    C.VACUUM_CUP: (("release_factor",), 1.15),
}


def definition(ctype: ComponentType) -> str:
    cols, thr = LABELS[ctype]
    return f"SIMULATED truth: max({', '.join(cols)}) >= {thr:g} in the window -> degraded"


def label(ctype: ComponentType, truth_row: dict[str, str]) -> int | None:
    cols, thr = LABELS[ctype]
    vals = [float(truth_row[c]) for c in cols if truth_row.get(c)]
    return int(max(vals) >= thr) if vals else None
