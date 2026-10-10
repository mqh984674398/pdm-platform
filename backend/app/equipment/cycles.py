"""Movement cycles (L3-04): actuator operations and motion segments.

Actuator duration signals report one value per operation (cylinder extend/retract, vacuum release).
An operation that does not finish is reported with the controller's timeout value instead of a real
duration. Such operations are flagged incomplete and get no duration, so a timeout never enters
duration statistics (S18). The timeout comes from configuration when known; otherwise it is inferred
as the value repeated among durations far above the period's typical one. Other far-off values (for
example a unit error, S16) are marked implausible and also kept out of duration statistics.

Motion segments are runs of samples in one direction on a speed signal.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from app.core.schemas import TimeWindow
from app.equipment.schemas import CycleKind, CycleSummary, MotionDirection, MovementCycle
from app.equipment.state import Series, is_operation, is_speed

INCOMPLETE_FACTOR = 3.0  # without a configured timeout: values this many times the median are incomplete
MIN_COMPLETED = 10  # completed operations needed before duration statistics are meaningful
MOTION_FRACTION = 0.1  # of the window's 95th percentile speed

_KIND_WORDS = (
    ("extend", CycleKind.EXTEND),
    ("retract", CycleKind.RETRACT),
    ("release", CycleKind.VACUUM_RELEASE),
)


@dataclass(frozen=True)
class CycleSignal:
    signal_id: str
    kind: CycleKind
    timeout_s: float | None = None


def infer_kind(s: Series) -> CycleKind | None:
    """Kind from the signal id or English name; configure CycleSignal explicitly when this fails."""
    text = f"{s.signal.signal_id} {s.signal.name.en}".lower()
    return next((k for word, k in _KIND_WORDS if word in text), None)


def _dt(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, UTC)


@dataclass(frozen=True)
class Classified:
    incomplete: np.ndarray  # reported the timeout: the operation did not finish
    implausible: np.ndarray  # far from typical but not the timeout (e.g. a unit error): excluded, reported
    timeout_s: float | None
    inferred: bool

    @property
    def usable(self) -> np.ndarray:
        return ~(self.incomplete | self.implausible)


def classify(v: np.ndarray, timeout_s: float | None) -> Classified:
    """Values must be non-missing. Without a configured timeout, the timeout is the value repeated among
    the outliers (controllers report one fixed timeout); outliers that differ from it are implausible."""
    none = np.zeros(v.size, bool)
    med = float(np.median(v)) if v.size >= 3 else 0.0
    outlier = v >= INCOMPLETE_FACTOR * med if med > 0 else none
    if timeout_s is not None:
        incomplete = v >= timeout_s * (1 - 1e-9)
        return Classified(incomplete, outlier & ~incomplete, timeout_s, False)
    if not outlier.any():
        return Classified(none, none, None, False)
    values, counts = np.unique(v[outlier], return_counts=True)
    if counts.max() < 2:
        return Classified(none, outlier, None, False)
    timeout = float(values[np.argmax(counts)])
    incomplete = outlier & (v == timeout)
    return Classified(incomplete, outlier & ~incomplete, timeout, True)


def operation_cycles(
    s: Series,
    lifecycle_id: str,
    window: TimeWindow,
    config: CycleSignal | None = None,
    min_completed: int = MIN_COMPLETED,
) -> tuple[list[MovementCycle], CycleSummary]:
    kind = config.kind if config else infer_kind(s)
    if kind is None or not is_operation(s) or s.component_id is None:
        raise ValueError(f"'{s.signal.signal_id}' is not an actuator operation signal")
    t, v = s.between(window.start.timestamp(), window.end.timestamp())
    keep = ~np.isnan(v)
    t, v = t[keep], v[keep]
    c = classify(v, config.timeout_s if config else None)
    cycles = []
    for i, (ts, val) in enumerate(zip(t, v, strict=True)):
        done = not c.incomplete[i]
        cycles.append(
            MovementCycle(
                cycle_id=f"{s.signal.signal_id}@{ts:.3f}",
                component_id=s.component_id,
                lifecycle_id=lifecycle_id,
                kind=kind,
                start=_dt(ts),
                end=_dt(ts + val) if done else None,
                duration_s=float(val) if done else None,
                complete=done,
                plausible=not c.implausible[i],
                signal_id=s.signal.signal_id,
                is_simulated=s.is_simulated,
            )
        )
    good = v[c.usable]
    summary = CycleSummary(
        signal_id=s.signal.signal_id,
        component_id=s.component_id,
        kind=kind,
        window=window,
        operation_count=int(v.size),
        completed_count=int(good.size),
        incomplete_count=int(c.incomplete.sum()),
        implausible_count=int(c.implausible.sum()),
        timeout_s=c.timeout_s,
        timeout_inferred=c.inferred,
        median_duration_s=float(np.median(good)) if good.size else None,
        sufficient=good.size >= min_completed,
        min_completed=min_completed,
        is_simulated=s.is_simulated,
    )
    return cycles, summary


def motion_segments(
    s: Series, lifecycle_id: str, windows: Sequence[tuple[float, float]]
) -> list[MovementCycle]:
    """Runs of moving samples in one direction inside each observation window. A run touching the
    window edge is incomplete: its true start or end was not observed."""
    if not is_speed(s) or s.component_id is None:
        raise ValueError(f"'{s.signal.signal_id}' is not a speed signal")
    out = []
    for t0, t1 in windows:
        t, v = s.between(t0, t1)
        ok = ~np.isnan(v)
        if ok.sum() < 5:
            continue
        thr = MOTION_FRACTION * float(np.percentile(np.abs(v[ok]), 95))
        sign = np.where(ok & (np.abs(v) > thr), np.sign(v), 0)
        edges = np.flatnonzero(np.diff(sign) != 0) + 1
        for run in np.split(np.arange(v.size), edges):
            d = sign[run[0]]
            if d == 0:
                continue
            a, b = float(t[run[0]]), float(t[run[-1]])
            done = run[0] > 0 and run[-1] < v.size - 1
            out.append(
                MovementCycle(
                    cycle_id=f"{s.signal.signal_id}@{a:.3f}",
                    component_id=s.component_id,
                    lifecycle_id=lifecycle_id,
                    kind=CycleKind.MOTION_SEGMENT,
                    start=_dt(a),
                    end=_dt(b),
                    duration_s=b - a,
                    complete=bool(done),
                    direction=MotionDirection.FORWARD if d > 0 else MotionDirection.REVERSE,
                    signal_id=s.signal.signal_id,
                    is_simulated=s.is_simulated,
                )
            )
    return out
