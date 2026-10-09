"""Per-window feature vectors for each component (L4-03, L4-04).

A vector describes one component over one closed observation window of a running machine and is
computed from that window's rows only. Rows after ``as_of`` are dropped before anything is computed,
and a window still open at ``as_of`` (it could grow with later rows) is not emitted, so a vector
never changes when later data arrives. The regime catalog used for residuals must be learned from a
period that ends before the extraction window starts.

Each vector carries the component's lifecycle for that window, the matched regime (or why there is
none), the source signals and the feature set version. Windows overlapping maintenance, or spanning
a lifecycle change, get no vector and are listed as skipped.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime

import numpy as np

from app.core.schemas import LocalizedText, TimeWindow
from app.equipment.cycles import CycleSignal, classify, infer_kind
from app.equipment.regimes import (
    CRUISE_FRACTION,
    comparable,
    has_regime_evidence,
    match,
    normalized,
    torque_speed_pairs,
    window_features,
)
from app.equipment.schemas import (
    ComponentType,
    CycleKind,
    KnownRegime,
    OperatingState,
    RegimeCatalog,
    RegimeStatus,
)
from app.equipment.state import (
    WINDOW_BREAK_MIN_S,
    Series,
    is_operation,
    is_speed,
    observation_windows,
    window_state,
)
from app.monitoring.features.definitions import FEATURE_SETS, MIN_OPERATIONS
from app.monitoring.schemas import FeatureExtraction, FeatureSkip, FeatureVector
from app.signals.schemas import PhysicalQuantity

RIPPLE_BAND = 0.2  # cruise samples within this share of the cruise level measure ripple
MOTION_FRACTION = 0.1  # samples above this share of the window's 95th percentile speed are moving
OPERATION_NAMES = {
    CycleKind.EXTEND: "extend",
    CycleKind.RETRACT: "retract",
    CycleKind.VACUUM_RELEASE: "release",
}

REASONS = {
    "maintenance": LocalizedText(zh="窗口与维护时段重叠", en="Window overlaps maintenance"),
    "lifecycle_change": LocalizedText(zh="窗口跨越部件更换", en="Window spans a component replacement"),
    "no_lifecycle": LocalizedText(zh="窗口内无已安装的生命周期", en="No installed lifecycle for the window"),
}

Lifecycles = Mapping[str, Sequence[tuple[str, datetime, datetime | None]]]


def _dt(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, UTC)


def _truncate(series: Sequence[Series], as_of: float) -> list[Series]:
    out = []
    for s in series:
        j = int(np.searchsorted(s.t, as_of, "right"))
        out.append(replace(s, t=s.t[:j], v=s.v[:j]))
    return out


def _break_s(series: Sequence[Series]) -> float:
    sampled = [s.signal.expected_sampling_s for s in series if s.signal.expected_sampling_s]
    return max(WINDOW_BREAK_MIN_S, 30 * min(sampled)) if sampled else WINDOW_BREAK_MIN_S


def closed_windows(series: Sequence[Series], as_of: float) -> list[tuple[float, float]]:
    """Observation windows that can no longer grow: followed by a later row, or by a pause at ``as_of``
    longer than the window break."""
    wins = observation_windows(series)
    if wins and as_of - wins[-1][1] <= _break_s(series):
        wins = wins[:-1]
    return wins


def _lifecycle(entries: Sequence[tuple[str, datetime, datetime | None]], t0: float, t1: float) -> str | None:
    """The lifecycle installed for the whole window; '' when the window spans a change."""
    touching = [lc for lc, a, b in entries if a.timestamp() <= t1 and (b is None or b.timestamp() > t0)]
    covering = [lc for lc, a, b in entries if a.timestamp() <= t0 and (b is None or b.timestamp() > t1)]
    if covering:
        return covering[0]
    return "" if touching else None


def _rms(x: np.ndarray) -> float | None:
    return float(np.sqrt(np.mean(x**2))) if x.size else None


def _axis_values(
    speed: Series | None,
    torque: Series | None,
    t0: float,
    t1: float,
    feats: Mapping[str, float],
    known: KnownRegime | None,
    pairs: Mapping[str, str],
    tolerance: float,
) -> dict[str, float | None]:
    vals: dict[str, float | None] = dict.fromkeys(
        [
            "speed_cruise",
            "speed_rms",
            "speed_ripple",
            "torque_cruise",
            "torque_rms",
            "torque_p95",
            "torque_cruise_residual",
        ]
    )
    if speed is not None:
        _, v = speed.between(t0, t1)
        av = np.abs(v[~np.isnan(v)])
        if av.size:
            vals["speed_cruise"] = feats.get(f"{speed.signal.signal_id}:cruise")
            p95 = float(np.percentile(av, 95))
            vals["speed_rms"] = _rms(av[av > MOTION_FRACTION * p95])
            cruise = av[av >= CRUISE_FRACTION * p95]
            level = float(np.median(cruise)) if cruise.size else 0.0
            near = cruise[np.abs(cruise - level) <= RIPPLE_BAND * level]  # ramp samples excluded
            if near.size >= 5 and level > 0:
                vals["speed_ripple"] = float(1.4826 * np.median(np.abs(near - level)) / level)
    if torque is not None:
        _, q = torque.between(t0, t1)
        aq = np.abs(q[~np.isnan(q)])
        fid = f"{torque.signal.signal_id}:cruise"
        vals["torque_cruise"] = feats.get(fid)
        vals["torque_rms"] = _rms(aq)
        vals["torque_p95"] = float(np.percentile(aq, 95)) if aq.size else None
        if known is not None and fid in feats:
            refs = {r.feature_id: r for r in known.reference}
            mid = {m.feature_id: m.median for m in known.match_features}
            if fid in refs and comparable(fid, feats, mid, pairs, tolerance):
                vals["torque_cruise_residual"] = normalized(feats[fid], refs[fid])
    return vals


def _actuator_values(
    ops: Sequence[tuple[str, Series, CycleSignal | None]],
    names: Sequence[str],
    t0: float,
    t1: float,
    known: KnownRegime | None,
) -> dict[str, float | None]:
    vals: dict[str, float | None] = {"operation_count": 0.0}
    for n in names:
        vals |= dict.fromkeys([f"{n}_median", f"{n}_p90", f"{n}_incomplete_ratio", f"{n}_residual"])
    refs = {r.feature_id: r for r in known.reference} if known else {}
    for name, s, cfg in ops:
        _, v = s.between(t0, t1)
        v = v[~np.isnan(v)]
        vals["operation_count"] = (vals["operation_count"] or 0.0) + v.size
        if not v.size:
            continue
        c = classify(v, cfg.timeout_s if cfg else None)
        good = v[c.usable]
        vals[f"{name}_incomplete_ratio"] = float(c.incomplete.sum() / v.size)
        if good.size >= MIN_OPERATIONS:
            med = float(np.median(good))
            vals[f"{name}_median"] = med
            vals[f"{name}_p90"] = float(np.percentile(good, 90))
            ref = refs.get(f"{s.signal.signal_id}:median")
            if ref is not None:
                vals[f"{name}_residual"] = normalized(med, ref)
    return vals


def extract_features(
    series: Sequence[Series],
    window: TimeWindow,
    components: Mapping[str, ComponentType],
    lifecycles: Lifecycles,
    catalog: RegimeCatalog | None = None,
    maintenance: Sequence[tuple[datetime, datetime, str]] = (),
    cycle_config: Mapping[str, CycleSignal] | None = None,
    as_of: datetime | None = None,
) -> FeatureExtraction:
    """``components`` maps component id to type; ``lifecycles`` maps component id to its
    (lifecycle_id, installed_at, retired_at) entries. ``as_of`` defaults to the window end."""
    cycle_config = cycle_config or {}
    a, b = window.start.timestamp(), window.end.timestamp()
    cut = min(b, (as_of or window.end).timestamp())
    if catalog is not None and catalog.learned_from.end > window.start:
        raise ValueError("the regime catalog must be learned from a period before the extraction window")
    series = _truncate(series, cut)
    sim = any(s.is_simulated for s in series)
    by_comp: dict[str, list[Series]] = {}
    for s in series:
        if s.component_id in components:
            by_comp.setdefault(s.component_id, []).append(s)
    not_supported = sorted(c for c, t in components.items() if t not in FEATURE_SETS)
    pairs = torque_speed_pairs(series)
    maint = [(m0.timestamp(), m1.timestamp()) for m0, m1, _ in maintenance]
    vectors, skipped = [], []

    for t0, t1 in closed_windows(series, cut):
        if t0 < a:
            continue
        if window_state(series, t0, t1)[0] != OperatingState.RUNNING:
            continue
        win = TimeWindow(start=_dt(t0), end=_dt(max(t1, t0 + 1e-3)))
        in_maint = any(m0 <= t1 and m1 >= t0 for m0, m1 in maint)
        feats = window_features(series, t0, t1, cycle_config)
        status, known = RegimeStatus.NOT_EVALUATED, None
        if catalog is not None and has_regime_evidence(series, feats):
            known = match(feats, catalog)
            status = RegimeStatus.KNOWN if known else RegimeStatus.UNSUPPORTED
        for cid, ctype in sorted(components.items()):
            fs = FEATURE_SETS.get(ctype)
            mine = by_comp.get(cid, [])
            if fs is None or not mine:
                continue
            if in_maint:
                skipped.append(FeatureSkip(component_id=cid, window=win, reason=REASONS["maintenance"]))
                continue
            lc = _lifecycle(lifecycles.get(cid, ()), t0, t1)
            if not lc:
                why = "no_lifecycle" if lc is None else "lifecycle_change"
                skipped.append(FeatureSkip(component_id=cid, window=win, reason=REASONS[why]))
                continue
            if ctype in (ComponentType.BALL_SCREW, ComponentType.LINEAR_MOTOR):
                speed = next((s for s in mine if is_speed(s)), None)
                torque = next((s for s in mine if s.signal.quantity == PhysicalQuantity.TORQUE), None)
                tol = catalog.tolerance if catalog else 0.0
                values = _axis_values(speed, torque, t0, t1, feats, known, pairs, tol)
                used = [s for s in (speed, torque) if s is not None]
            else:
                names = [f.name.removesuffix("_median") for f in fs.features if f.name.endswith("_median")]
                ops = []
                for s in mine:
                    cfg = cycle_config.get(s.signal.signal_id)
                    kind = cfg.kind if cfg else infer_kind(s)
                    if is_operation(s) and kind in OPERATION_NAMES and OPERATION_NAMES[kind] in names:
                        ops.append((OPERATION_NAMES[kind], s, cfg))
                values = _actuator_values(ops, names, t0, t1, known)
                used = [s for _, s, _ in ops]
            vectors.append(
                FeatureVector(
                    component_id=cid,
                    lifecycle_id=lc,
                    regime_id=known.regime.regime_id if known else None,
                    regime_status=status.value,
                    catalog_id=catalog.catalog_id if catalog else None,
                    feature_ref=fs.ref,
                    window=win,
                    source_signals=sorted(s.signal.signal_id for s in used),
                    values={f.name: values.get(f.name) for f in fs.features},
                    is_simulated=any(s.is_simulated for s in mine),
                )
            )
    return FeatureExtraction(vectors=vectors, skipped=skipped, not_supported=not_supported, is_simulated=sim)
