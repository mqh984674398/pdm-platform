"""Operating regimes (L3-03) and condition-normalized residuals (L4-03).

Each running observation window is characterized by per-signal features: cruise speed of each speed
signal, torque at cruise of each torque signal, and the median completed duration of each actuator
signal. Regimes are learned from a reference period the user confirms as known operation: windows are
grouped by their speed features, and groups seen often enough become known regimes.

Only speed features and the operation interval (time between actuator operations, which follows the
machine cycle) decide the regime. Torque and durations also move when a component degrades, so
letting them define regimes would hide degradation as a "new regime". They are normalized against
the matched regime's reference levels instead, which is what keeps a recipe change from looking like
degradation (S02). A running window whose speeds match no known regime is UNSUPPORTED (S17): health
and predictions must abstain there rather than extrapolate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

import numpy as np

from app.core.schemas import LocalizedText, TimeWindow
from app.equipment.cycles import CycleSignal, classify
from app.equipment.schemas import (
    AccelerationPhase,
    FeatureStats,
    FeatureValue,
    KnownRegime,
    MotionDirection,
    OperatingRegime,
    OperatingState,
    RegimeAssignment,
    RegimeCatalog,
    RegimeStatus,
)
from app.equipment.state import Series, is_operation, is_speed, moving, observation_windows, window_state
from app.signals.schemas import PhysicalQuantity

TOLERANCE = 0.1  # relative, on each speed feature
# Moves are sampled at fixed intervals, so a window can miss the cruise phase and see only ramp values:
# a sampled speed peak can fall short of the cruise speed (by up to ~30 % for short cruise phases) but
# cannot exceed it beyond noise. Speed matching is one-sided for that reason.
ALIAS_UNDERSHOOT = 0.3
INTERVAL_TOLERANCE = 0.05  # operation intervals (time between actuator operations) are precise
MIN_INTERVAL_EVENTS = 5
MIN_REGIME_WINDOWS = 3
CRUISE_FRACTION = 0.8  # samples at or above this share of the 95th percentile speed are cruising

REASONS = {
    RegimeStatus.KNOWN: LocalizedText(zh="速度特征匹配已知工况", en="Speed features match a known regime"),
    RegimeStatus.UNSUPPORTED: LocalizedText(
        zh="运行条件不属于任何已知工况，预测须弃权",
        en="Running outside every known regime: predictions must abstain",
    ),
    "not_running": LocalizedText(zh="非运行状态，不判断工况", en="Not running: regime not evaluated"),
    "no_speed": LocalizedText(
        zh="无速度信号，无法判断工况", en="No speed signal: regime cannot be characterized"
    ),
    "no_catalog": LocalizedText(zh="尚无已知工况目录", en="No regime catalog yet"),
}


def _mad(x: np.ndarray) -> float:
    return float(1.4826 * np.median(np.abs(x - np.median(x)))) if x.size else 0.0


def window_features(
    series: Sequence[Series], t0: float, t1: float, cycle_config: Mapping[str, CycleSignal] | None = None
) -> dict[str, float]:
    cycle_config = cycle_config or {}
    feats: dict[str, float] = {}
    cruise_times: dict[str | None, np.ndarray] = {}
    for s in series:
        if not is_speed(s):
            continue
        t, v = s.between(t0, t1)
        ok = ~np.isnan(v)
        if not moving(v):
            continue
        av = np.abs(v[ok])
        cruise = av >= CRUISE_FRACTION * float(np.percentile(av, 95))
        feats[f"{s.signal.signal_id}:cruise"] = float(np.median(av[cruise]))
        cruise_times.setdefault(s.component_id, t[ok][cruise])
    for s in series:
        if s.signal.quantity == PhysicalQuantity.TORQUE and s.component_id in cruise_times:
            t, q = s.between(t0, t1)
            ok = ~np.isnan(q)
            t, q = t[ok], q[ok]
            ct = cruise_times[s.component_id]
            if t.size == 0 or ct.size == 0:
                continue
            tol = 0.5 * (s.signal.expected_sampling_s or 1.0)
            idx = np.clip(np.searchsorted(t, ct), 0, t.size - 1)
            near = np.abs(t[idx] - ct) <= tol
            if near.any():
                feats[f"{s.signal.signal_id}:cruise"] = float(np.median(np.abs(q[idx[near]])))
        elif is_operation(s):
            t, v = s.between(t0, t1)
            if t.size >= MIN_INTERVAL_EVENTS:
                feats[f"{s.signal.signal_id}:interval"] = float(np.median(np.diff(t)))
            v = v[~np.isnan(v)]
            cfg = cycle_config.get(s.signal.signal_id)
            usable = classify(v, cfg.timeout_s if cfg else None).usable
            if usable.any():
                feats[f"{s.signal.signal_id}:median"] = float(np.median(v[usable]))
    return feats


def _speed_keys(series: Sequence[Series]) -> list[str]:
    return sorted(f"{s.signal.signal_id}:cruise" for s in series if is_speed(s))


def _match_keys(series: Sequence[Series], rows: Sequence[Mapping[str, float]]) -> list[str]:
    """Speed features, plus operation intervals that every reference window has."""
    intervals = sorted({k for r in rows for k in r if k.endswith(":interval")})
    return _speed_keys(series) + [k for k in intervals if all(k in r for r in rows)]


def _deviation(fid: str, x: float, center: float, tol: float, one_sided: bool) -> float | None:
    """Relative deviation when ``x`` fits ``center``, else None."""
    dev = (x - center) / max(abs(center), 1e-9)
    if fid.endswith(":interval"):
        return abs(dev) if abs(dev) <= INTERVAL_TOLERANCE else None
    low = -ALIAS_UNDERSHOOT if one_sided else -tol
    return abs(dev) if low <= dev <= tol else None


def _fit(f: Mapping[str, float], centers: Mapping[str, float], tol: float, one_sided: bool) -> float | None:
    devs = []
    for k, c in centers.items():
        if k not in f:
            return None
        d = _deviation(k, f[k], c, tol, one_sided)
        if d is None:
            return None
        devs.append(d)
    return max(devs) if devs else None


def _stats(fid: str, values: list[float]) -> FeatureStats:
    x = np.array(values)
    return FeatureStats(feature_id=fid, median=float(np.median(x)), mad=_mad(x), count=int(x.size))


def _close(x: float, center: float, tol: float) -> bool:
    return abs(x - center) <= tol * max(abs(center), 1e-9)


def torque_speed_pairs(series: Sequence[Series]) -> dict[str, str]:
    """Torque feature id -> speed feature id of the same component."""
    speed = {s.component_id: f"{s.signal.signal_id}:cruise" for s in series if is_speed(s) and s.component_id}
    return {
        f"{s.signal.signal_id}:cruise": speed[s.component_id]
        for s in series
        if s.signal.quantity == PhysicalQuantity.TORQUE and s.component_id in speed
    }


def comparable(
    fid: str,
    feats: Mapping[str, float],
    centers: Mapping[str, float],
    pairs: Mapping[str, str],
    tol: float = TOLERANCE,
) -> bool:
    """Torque at cruise is only comparable when the window actually sampled the cruise phase: a window
    whose speed peak fell short saw ramp torque, which includes acceleration torque."""
    if fid not in pairs:
        return True
    speed = pairs[fid]
    if speed not in feats or speed not in centers:
        return False
    return _deviation(speed, feats[speed], centers[speed], tol, False) is not None


def learn_catalog(
    series: Sequence[Series],
    machine_id: str,
    reference: TimeWindow,
    catalog_id: str,
    tolerance: float = TOLERANCE,
    min_windows: int = MIN_REGIME_WINDOWS,
    cycle_config: Mapping[str, CycleSignal] | None = None,
) -> RegimeCatalog:
    """Group the reference period's running windows by speed features into known regimes."""
    speed_keys = _speed_keys(series)
    a, b = reference.start.timestamp(), reference.end.timestamp()
    rows: list[dict[str, float]] = []
    for t0, t1 in observation_windows(series):
        if t0 < a or t1 > b or window_state(series, t0, t1)[0] != OperatingState.RUNNING:
            continue
        f = window_features(series, t0, t1, cycle_config)
        if speed_keys and all(k in f for k in speed_keys):
            rows.append(f)
    keys = _match_keys(series, rows)

    def centers(c: list[dict[str, float]]) -> dict[str, float]:
        return {k: float(np.median([r[k] for r in c])) for k in keys}

    # pass 1: tight groups; pass 2: groups whose speeds only fall short of a larger group's (sampling
    # missed the cruise phase) and whose intervals agree join that group
    clusters: list[list[dict[str, float]]] = []
    for f in sorted(rows, key=lambda r: [-r[k] for k in keys]):
        fits = [(d, c) for c in clusters if (d := _fit(f, centers(c), tolerance, False)) is not None]
        if fits:
            min(fits, key=lambda x: x[0])[1].append(f)
        else:
            clusters.append([f])
    # roots are the groups with the highest speeds; a group sampled short joins the closest root above it
    clusters.sort(key=lambda c: [-centers(c)[k] for k in keys])
    merged: list[tuple[dict[str, float], list[dict[str, float]]]] = []
    for c in clusters:
        mine = centers(c)
        fits = [(d, m) for m in merged if (d := _fit(mine, m[0], tolerance, True)) is not None]
        if fits:
            min(fits, key=lambda x: x[0])[1][1].extend(c)
        else:
            merged.append((mine, list(c)))
    merged.sort(key=lambda m: [m[0][k] for k in keys])
    pairs = torque_speed_pairs(series)
    regimes = []
    for root, c in (m for m in merged if len(m[1]) >= min_windows):
        rid = f"RG{len(regimes) + 1}"
        fids = sorted({k for r in c for k in r})
        ref = [
            _stats(k, vals)
            for k in fids
            if (vals := [r[k] for r in c if k in r and comparable(k, r, root, pairs)])
        ]
        match = []
        for k in keys:  # centered on the root: its windows sampled the cruise phase
            tight = np.array([r[k] for r in c if _deviation(k, r[k], root[k], tolerance, False) is not None])
            match.append(FeatureStats(feature_id=k, median=root[k], mad=_mad(tight), count=int(tight.size)))
        speed = ", ".join(
            f"{x.feature_id.split(':')[0]}≈{x.median:.4g}" for x in match if x.feature_id in speed_keys
        )
        load = ", ".join(f"{x.feature_id.split(':')[0]}≈{x.median:.3g}" for x in ref if x.feature_id in pairs)
        regime = OperatingRegime(
            regime_id=rid,
            speed_band=speed,
            direction=MotionDirection.UNKNOWN,  # moves alternate direction inside every window
            phase=AccelerationPhase.CONSTANT,  # features describe the cruise phase
            load_class=load or None,
            recipe=None,  # no recipe signal in the source
            supported=True,
        )
        regimes.append(KnownRegime(regime=regime, match_features=match, reference=ref, window_count=len(c)))
    return RegimeCatalog(
        catalog_id=catalog_id,
        machine_id=machine_id,
        learned_from=reference,
        tolerance=tolerance,
        regimes=regimes,
        is_simulated=any(s.is_simulated for s in series),
    )


def match(features: Mapping[str, float], catalog: RegimeCatalog) -> KnownRegime | None:
    """Closest known regime whose match features all fit, preferring a fit within tolerance over a
    fit that needs the sampling allowance."""
    best: tuple[int, float, KnownRegime] | None = None
    for r in catalog.regimes:
        centers = {m.feature_id: m.median for m in r.match_features}
        for rank, one_sided in ((0, False), (1, True)):
            d = _fit(features, centers, catalog.tolerance, one_sided)
            if d is not None:
                if best is None or (rank, d) < best[:2]:
                    best = (rank, d, r)
                break
    return best[2] if best else None


def normalized(value: float, ref: FeatureStats) -> float:
    """Condition-normalized residual: distance from the regime's reference level in robust units."""
    scale = max(ref.mad, 0.01 * abs(ref.median), 1e-9)
    return (value - ref.median) / scale


def _dt(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, UTC)


def assign_regimes(
    series: Sequence[Series],
    window: TimeWindow,
    catalog: RegimeCatalog | None,
    cycle_config: Mapping[str, CycleSignal] | None = None,
) -> list[RegimeAssignment]:
    a, b = window.start.timestamp(), window.end.timestamp()
    has_speed = any(is_speed(s) for s in series)
    pairs = torque_speed_pairs(series)
    out = []
    for t0, t1 in observation_windows(series):
        if t1 < a or t0 >= b:
            continue
        state, _, _ = window_state(series, t0, t1)
        feats = window_features(series, t0, t1, cycle_config) if state == OperatingState.RUNNING else {}
        values = [FeatureValue(feature_id=k, value=v) for k, v in sorted(feats.items())]
        status, rid, why = RegimeStatus.NOT_EVALUATED, None, "not_running"
        if state == OperatingState.RUNNING:
            keys = _speed_keys(series)
            if not has_speed or not all(k in feats for k in keys):
                why = "no_speed"
            elif catalog is None:
                why = "no_catalog"
            else:
                known = match(feats, catalog)
                if known is None:
                    status, why = RegimeStatus.UNSUPPORTED, RegimeStatus.UNSUPPORTED
                else:
                    status, rid, why = RegimeStatus.KNOWN, known.regime.regime_id, RegimeStatus.KNOWN
                    refs = {r.feature_id: r for r in known.reference}
                    mid = {m.feature_id: m.median for m in known.match_features}
                    values = [
                        v.model_copy(update={"normalized": normalized(v.value, refs[v.feature_id])})
                        if v.feature_id in refs
                        and comparable(v.feature_id, feats, mid, pairs, catalog.tolerance)
                        else v
                        for v in values
                    ]
        out.append(
            RegimeAssignment(
                start=_dt(t0),
                end=_dt(max(t1, t0 + 1e-3)),
                state=state,
                status=status,
                regime_id=rid,
                features=values,
                reason=REASONS[why],
            )
        )
    return out
