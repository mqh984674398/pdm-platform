"""Bounded candidate configurations (OPT-01 Path A, OPT-02 Path B) and the safety invariant (OPT-05).

Path A changes rule-engine parameters and STATISTICAL thresholds only. Path B changes the decision
post-processing (aging grading). SAFETY rules are never changed, removed or disabled: a candidate
that differs from the champion in any SAFETY rule is refused.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from app.decision.aging import AgingPolicy
from app.monitoring.schemas import RuleKind, RuleSet

PATH_A = {
    "persistence": (2, 3, 4),
    "hold": (2, 3, 4),
    "cusum_k": (1.5, 2.0, 2.5),
    "cusum_h": (10.0, 12.0, 16.0),
    "threshold_scale": (0.9, 1.0, 1.2),
}
PATH_B = {
    "aging_max_rate": (0.15, 0.2, 0.25),
    "aging_min_age_days": (21.0, 30.0, 45.0),
    "aging_max_step": (2.0, 2.5, 3.0),
}


class SafetyChangeError(ValueError):
    pass


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    path: str
    rules: RuleSet
    policy: AgingPolicy
    changes: dict[str, float]


def check_safety(champion: RuleSet, candidate: RuleSet) -> None:
    mine = {r.rule_id: r for r in champion.rules if r.kind == RuleKind.SAFETY}
    theirs = {r.rule_id: r for r in candidate.rules if r.kind == RuleKind.SAFETY}
    if mine != theirs:
        changed = sorted(set(mine) ^ set(theirs) | {k for k in mine if k in theirs and mine[k] != theirs[k]})
        raise SafetyChangeError(f"candidate changes safety rules {changed}; safety rules are never optimized")


def apply_a(rules: RuleSet, ch: dict[str, float], cid: str) -> RuleSet:
    s = ch.get("threshold_scale", 1.0)
    new = [
        r.model_copy(update={k: getattr(r, k) * s for k in ("watch", "warning", "critical") if getattr(r, k)})
        if r.kind == RuleKind.STATISTICAL
        else r
        for r in rules.rules
    ]
    fields = {
        k: (int(v) if k in ("persistence", "hold") else v) for k, v in ch.items() if k in RuleSet.model_fields
    }
    out = rules.model_copy(update={**fields, "rules": new, "version": f"{rules.version}+{cid}"})
    check_safety(rules, out)
    return out


def apply_b(policy: AgingPolicy, ch: dict[str, float], cid: str) -> AgingPolicy:
    m = {
        "aging_max_rate": "max_rate_per_day",
        "aging_min_age_days": "min_age_days",
        "aging_max_step": "max_step",
    }
    return replace(policy, **{m[k]: v for k, v in ch.items() if k in m}, version=f"{policy.version}+{cid}")


def generate(rules: RuleSet, policy: AgingPolicy, n: int, seed: int) -> list[Candidate]:
    """``n`` distinct candidates, alternating Path A and Path B, each one parameter set from the grid."""
    rng = np.random.default_rng(seed)
    out, seen = [], set()
    for _ in range(n * 20):
        if len(out) >= n:
            break
        path, grid = ("A", PATH_A) if len(out) % 2 == 0 else ("B", PATH_B)
        ch = {k: float(rng.choice(v)) for k, v in grid.items()}
        key = (path, tuple(sorted(ch.items())))
        current = {
            "persistence": rules.persistence,
            "hold": rules.hold,
            "cusum_k": rules.cusum_k,
            "cusum_h": rules.cusum_h,
            "threshold_scale": 1.0,
            "aging_max_rate": policy.max_rate_per_day,
            "aging_min_age_days": policy.min_age_days,
            "aging_max_step": policy.max_step,
        }
        if key in seen or all(current[k] == v for k, v in ch.items()):
            continue
        seen.add(key)
        cid = f"{path}{len(out) + 1:02d}"
        if path == "A":
            out.append(Candidate(cid, path, apply_a(rules, ch, cid), policy, ch))
        else:
            out.append(Candidate(cid, path, rules, apply_b(policy, ch, cid), ch))
    return out
