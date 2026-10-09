"""Evaluate a rule set on a component's feature windows (L4-07, L6-03).

Deterministic: the same vectors, references, rule set and settings always give the same result.
Windows are taken in time order per lifecycle; persistence, CUSUM and hysteresis restart with each
lifecycle because each lifecycle has its own verified reference. A level rises at once and drops only
after ``hold`` windows below it.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence

from app.monitoring.baselines.stats import deviation
from app.monitoring.features.definitions import FEATURE_SETS
from app.monitoring.rules.statistics import cusum_upper, ewma, running_median
from app.monitoring.schemas import (
    Baseline,
    FeatureStats,
    FeatureVector,
    MonitoringLevel,
    RuleDefinition,
    RuleHit,
    RuleKind,
    RuleSet,
    WindowEvaluation,
)

L = MonitoringLevel
ORDER = [L.NORMAL, L.WATCH, L.WARNING, L.CRITICAL]


def component_type(feature_ref: str) -> str | None:
    name = feature_ref.split("@")[0]
    return next((t.value for t, fs in FEATURE_SETS.items() if fs.feature_set == name), None)


def level_for(value: float, rule: RuleDefinition) -> MonitoringLevel:
    for lvl, thr in ((L.CRITICAL, rule.critical), (L.WARNING, rule.warning), (L.WATCH, rule.watch)):
        if thr is not None and value >= thr:
            return lvl
    return L.NORMAL


def _threshold(rule: RuleDefinition, lvl: MonitoringLevel) -> float:
    return {L.WATCH: rule.watch, L.WARNING: rule.warning, L.CRITICAL: rule.critical}[lvl] or 0.0


def _ref_stats(ref: Baseline, regime_id: str | None, feature: str) -> FeatureStats | None:
    return ref.regime_stats.get(regime_id or "", {}).get(feature) or ref.stats.get(feature)


def _held(levels: list[MonitoringLevel], hold: int) -> MonitoringLevel:
    return max(levels[-hold:], key=ORDER.index) if levels else L.NORMAL


def evaluate(
    vectors: Sequence[FeatureVector],
    references: Mapping[str, Baseline],
    rules: RuleSet,
    disabled: Collection[str] = (),
    limits: Mapping[str, float] | None = None,
    rules_version: str | None = None,
) -> list[WindowEvaluation]:
    """``references`` maps lifecycle id to its verified healthy reference; ``limits`` maps component
    id to its torque limit (Nm) for SF-TORQUE-LIMIT."""
    limits = limits or {}
    version = rules_version or rules.ref
    out: list[WindowEvaluation] = []
    by_lc: dict[tuple[str, str], list[FeatureVector]] = {}
    for v in sorted(vectors, key=lambda v: v.window.start):
        by_lc.setdefault((v.component_id, v.lifecycle_id), []).append(v)
    for (cid, lc), vs in by_lc.items():
        ctype = component_type(vs[0].feature_ref)
        active = [r for r in rules.rules if ctype in r.component_types and r.rule_id not in disabled]
        ref = references.get(lc)
        # per statistical rule: chosen feature and the deviation series over evaluated windows
        chosen: dict[str, str | None] = {}
        for r in active:
            if r.kind == RuleKind.STATISTICAL:
                chosen[r.rule_id] = next((f for f in r.features if ref and f in ref.stats), None)
        z: dict[str, list[float]] = {rid: [] for rid in chosen}
        held: dict[str, list[MonitoringLevel]] = {r.rule_id: [] for r in active}
        last_hit: dict[str, RuleHit] = {}
        cus_state: dict[str, float] = {}
        ew_state: dict[str, float] = {}
        for v in vs:
            hits, stats, missing = [], {}, []

            for r in active:
                if r.kind == RuleKind.STATISTICAL:
                    f = chosen[r.rule_id]
                    x = v.values.get(f) if f else None
                    st = _ref_stats(ref, v.regime_id, f) if (ref and f) else None
                    if f is None or ref is None:
                        missing.append(r.rule_id)
                        if (
                            r.rule_id in last_hit
                        ):  # an unevaluable window keeps the level; it does not clear it
                            hits.append(last_hit[r.rule_id])
                        continue
                    if x is None or st is None:
                        missing.append(r.rule_id)
                        if (
                            r.rule_id in last_hit
                        ):  # an unevaluable window keeps the level; it does not clear it
                            hits.append(last_hit[r.rule_id])
                        continue
                    zs = z[r.rule_id]
                    zs.append(deviation(x, st))
                    # one step of each sequential statistic (same values as over the whole series)
                    persistent = running_median(zs[-rules.persistence :], rules.persistence)[-1]
                    cus = cusum_upper([zs[-1]], rules.cusum_k, cus_state.get(r.rule_id, 0.0))[-1]
                    ew = ewma([zs[-1]], rules.ewma_lambda, ew_state.get(r.rule_id, 0.0))[-1]
                    cus_state[r.rule_id], ew_state[r.rule_id] = cus, ew
                    stats |= {f"{r.rule_id}:z": zs[-1], f"{r.rule_id}:ewma": ew, f"{r.rule_id}:cusum": cus}
                    lvl, value, basis = L.NORMAL, persistent if persistent is not None else 0.0, "persistent"
                    if persistent is not None:
                        stats[f"{r.rule_id}:persistent"] = persistent
                        lvl = level_for(persistent, r)
                    if lvl == L.NORMAL and cus >= rules.cusum_h:
                        lvl, value, basis = L.WATCH, cus, "cusum"
                    feature = f
                else:
                    if r.rule_id == "SF-TORQUE-LIMIT":
                        lim, x = limits.get(cid), v.values.get("torque_p95")
                        if lim is None or x is None:
                            missing.append(r.rule_id)
                            if (
                                r.rule_id in last_hit
                            ):  # an unevaluable window keeps the level; it does not clear it
                                hits.append(last_hit[r.rule_id])
                            continue
                        value, feature = x / lim, "torque_p95"
                    else:
                        present = [(v.values[f], f) for f in r.features if v.values.get(f) is not None]
                        if not present:
                            missing.append(r.rule_id)
                            if (
                                r.rule_id in last_hit
                            ):  # an unevaluable window keeps the level; it does not clear it
                                hits.append(last_hit[r.rule_id])
                            continue
                        value, feature = max(present)
                    lvl, basis = level_for(value, r), "raw"
                held[r.rule_id].append(lvl)
                final = _held(held[r.rule_id], rules.hold)
                last_hit.pop(r.rule_id, None)
                if final != L.NORMAL:
                    last_hit[r.rule_id] = RuleHit(
                        rule_id=r.rule_id,
                        kind=r.kind,
                        level=final,
                        feature=feature,
                        value=value,
                        threshold=rules.cusum_h
                        if basis == "cusum" and final == L.WATCH
                        else _threshold(r, final),
                        basis=basis,
                    )
                    hits.append(last_hit[r.rule_id])
            level = max((h.level for h in hits), key=ORDER.index, default=L.NORMAL)
            out.append(
                WindowEvaluation(
                    component_id=cid,
                    lifecycle_id=lc,
                    window=v.window,
                    feature_ref=v.feature_ref,
                    level=level,
                    evaluated=len(missing) < len(active),
                    hits=hits,
                    statistics=stats,
                    not_evaluated=missing,
                    rules_version=version,
                    is_simulated=v.is_simulated,
                )
            )
    return out
