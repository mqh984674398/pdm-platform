"""Time-ordered historical replay of the decision pipeline (T025 AC1, OPT-04).

Windows are processed in time order. Each decision uses only feature windows that ended at or before
it: the rule engine runs per lifecycle in time order (persistence, CUSUM, hysteresis are causal), and
fusion receives only the history up to the window. ``until`` truncates the input so a replay can be
checked for future leakage: decisions up to ``until`` must not change when later data is added.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.decision.aging import DEFAULT_POLICY, AgingPolicy
from app.decision.fusion import FusionInput, FusionResult, fuse
from app.equipment.schemas import ComponentLifecycle, ComponentType
from app.monitoring.rules.definitions import DEFAULT_RULES
from app.monitoring.rules.engine import evaluate
from app.monitoring.schemas import Baseline, FeatureVector, RuleSet


@dataclass(frozen=True)
class ComponentHistory:
    component_id: str
    component_type: ComponentType
    vectors: tuple[FeatureVector, ...]
    references: dict[str, Baseline]  # lifecycle id -> verified healthy reference
    lifecycles: dict[str, ComponentLifecycle]
    is_simulated: bool


def replay(
    h: ComponentHistory,
    rules: RuleSet = DEFAULT_RULES,
    policy: AgingPolicy = DEFAULT_POLICY,
    disabled: Sequence[str] = (),
    until: datetime | None = None,
) -> list[FusionResult]:
    vectors = sorted(
        (v for v in h.vectors if until is None or v.window.end <= until), key=lambda v: v.window.end
    )
    evals = sorted(evaluate(vectors, h.references, rules, disabled), key=lambda e: e.window.end)
    out, seen = [], {}
    for e in evals:
        hist = seen.setdefault(e.lifecycle_id, [])
        hist.append(e)
        if not e.evaluated or e.lifecycle_id not in h.references:
            continue
        lc = h.lifecycles.get(e.lifecycle_id)
        inp = FusionInput(
            h.component_id,
            h.component_type,
            e.lifecycle_id,
            lc.installed_at if lc else None,
            e,
            list(hist),
            is_simulated=h.is_simulated,
        )
        out.append(fuse(inp, policy))
    return out
