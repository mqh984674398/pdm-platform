"""Per-signal data quality (L4-01): missing, duplicate, out-of-order, jitter, gaps, sampling interval,
and unit plausibility, computed on full-resolution rows (L2-06).

Findings are reported, never corrected. Telemetry often arrives in short observation windows with long
pauses in between, so cadence checks (missing, jitter) run inside observation windows and the pause
length itself is the reference for gaps. Checks a signal or source cannot support are listed in
``not_evaluated`` rather than reported as clean.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from app.core.schemas import TimeWindow
from app.datasource.schemas import RawTelemetryRow
from app.monitoring.schemas import DataQualityReport, FlaggedSpan
from app.signals.normalize import convert
from app.signals.schemas import PhysicalQuantity, QualityFlag, SignalDefinition, UnitConversion

Q = QualityFlag

# Plausibility envelopes by unit, used for OUT_OF_RANGE when the signal defines no valid range.
DEFAULT_RANGES: dict[str, tuple[float, float]] = {
    "s": (0.0, 60.0),
    "ms": (0.0, 60_000.0),
    "rpm": (-20_000.0, 20_000.0),
    "mm/s": (-10_000.0, 10_000.0),
}
WINDOW_BREAK_MIN_S = 60.0  # pauses longer than max(this, 30 sample intervals) separate observation windows
MISSING_TOLERANCE = 0.02  # share of expected samples that may be absent before MISSING is raised
JITTER_TOLERANCE = 0.05  # robust interval spread, relative to the expected interval
GAP_FACTOR = 4.0  # a pause longer than this many typical pauses is a GAP
# Event-based signals report only while the machine operates, so idle stretches look like pauses too.
EVENT_GAP_FACTOR = 6.0
DEFAULT_GAP_S = 24 * 3600.0  # used when the typical pause cannot be estimated
UNIT_RATIO = 20.0  # level change between windows (or vs. reference) that suggests a unit/scale error
LEVEL_QUANTITIES = {PhysicalQuantity.DURATION, PhysicalQuantity.PRESSURE}  # strictly positive levels


@dataclass
class Rows:
    """Rows of one signal in timestamp order: epoch seconds, normalized values (nan = missing)."""

    t: np.ndarray
    v: np.ndarray
    arrival: np.ndarray | None  # None when the source does not expose storage order
    is_simulated: bool

    @classmethod
    def build(cls, rows: Sequence[RawTelemetryRow], conversion: UnitConversion | None) -> Rows:
        t = np.array([r.ts.timestamp() for r in rows], dtype=float)
        v = np.array([np.nan if r.value is None else convert(r.value, conversion) for r in rows], dtype=float)
        seqs = [r.arrival_seq for r in rows]
        arrival = np.array(seqs, dtype=float) if rows and all(s is not None for s in seqs) else None
        return cls(t=t, v=v, arrival=arrival, is_simulated=any(r.is_simulated for r in rows))


def observation_windows(t_unique: np.ndarray, expected_s: float | None) -> list[np.ndarray]:
    """Index groups of consecutive unique timestamps separated by pauses."""
    if t_unique.size == 0:
        return []
    d = np.diff(t_unique)
    base = expected_s or (float(np.median(d)) if d.size else 0.0)
    brk = max(WINDOW_BREAK_MIN_S, 30 * base)
    return np.split(np.arange(t_unique.size), np.flatnonzero(d > brk) + 1)


def _mad(x: np.ndarray) -> float:
    return float(1.4826 * np.median(np.abs(x - np.median(x)))) if x.size else 0.0


def _dt(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, UTC)


def typical_pause(t_unique: np.ndarray, expected_s: float | None) -> float | None:
    groups = observation_windows(t_unique, expected_s)
    pauses = [t_unique[b[0]] - t_unique[a[-1]] for a, b in zip(groups, groups[1:], strict=False)]
    return float(np.median(pauses)) if len(pauses) >= 2 else None


def _levels(rows: Rows, expected_s: float | None) -> list[float]:
    t_u, first = np.unique(rows.t, return_index=True)
    v_u = rows.v[first]
    out = []
    for g in observation_windows(t_u, expected_s):
        vals = v_u[g][~np.isnan(v_u[g])]
        if vals.size:
            out.append(float(np.median(np.abs(vals))))
    return out


def assess(
    signal: SignalDefinition,
    rows: Rows,
    window: TimeWindow,
    reference: Rows | None = None,
) -> DataQualityReport:
    """``rows`` cover ``window``; ``reference`` (optional) is the period just before it."""
    expected = signal.expected_sampling_s
    flags: set[QualityFlag] = set()
    not_evaluated: set[QualityFlag] = set()
    spans: list[FlaggedSpan] = []
    n = int(rows.t.size)

    # duplicates and missing values
    dup_mask = np.zeros(n, dtype=bool)
    if n > 1:
        dup_mask[1:] = rows.t[1:] == rows.t[:-1]
    duplicate_count = int(dup_mask.sum())
    null_count = int(np.isnan(rows.v).sum())

    # out-of-order delivery needs storage order
    ooo_mask = np.zeros(n, dtype=bool)
    if rows.arrival is None:
        not_evaluated.add(Q.OUT_OF_ORDER)
    elif n:
        order = np.argsort(rows.arrival, kind="stable")
        t_arr = rows.t[order]
        late = np.zeros(n, dtype=bool)
        late[1:] = t_arr[1:] < np.maximum.accumulate(t_arr)[:-1]
        ooo_mask[order] = late

    # cadence inside observation windows
    t_u, first = np.unique(rows.t, return_index=True)
    groups = observation_windows(t_u, expected)
    within = np.concatenate([np.diff(t_u[g]) for g in groups]) if groups else np.array([])
    median_interval = float(np.median(within)) if within.size else None
    jitter = _mad(within) if within.size >= 3 else None
    missing_by_cadence = 0
    if expected is None:
        not_evaluated.update({Q.MISSING, Q.JITTER})  # event-based: no expected cadence

    # plausibility range
    low, high = signal.valid_min, signal.valid_max
    if low is None and high is None and signal.unit in DEFAULT_RANGES:
        low, high = DEFAULT_RANGES[signal.unit]
    finite = ~np.isnan(rows.v)
    oor_mask = np.zeros(n, dtype=bool)
    if low is not None:
        oor_mask |= finite & (rows.v < low)
    if high is not None:
        oor_mask |= finite & (rows.v > high)
    valid_range = (low, high) if (low is not None or high is not None) else None
    if valid_range is None:
        not_evaluated.add(Q.OUT_OF_RANGE)

    # unit plausibility from level changes between windows and against the reference period
    ref_levels = _levels(reference, expected) if reference is not None and reference.t.size else []
    ref_level = float(np.median(ref_levels)) if len(ref_levels) >= 3 else None
    level_check = signal.quantity in LEVEL_QUANTITIES
    if not level_check:
        not_evaluated.add(Q.UNIT_SUSPECT)

    def suspicious(level: float, previous: float | None) -> bool:
        if not level_check or level <= 0:
            return False
        refs = [x for x in (previous, ref_level) if x and x > 0]
        return any(level / r >= UNIT_RATIO or r / level >= UNIT_RATIO for r in refs)

    # per observation window findings
    previous_level: float | None = None
    for g in groups:
        t0, t1 = float(t_u[g[0]]), float(t_u[g[-1]])
        in_win = (rows.t >= t0) & (rows.t <= t1)
        f: set[QualityFlag] = set()
        if expected:
            count = round((t1 - t0) / expected) + 1
            absent = max(0, count - g.size)
            missing_by_cadence += absent
            if absent > MISSING_TOLERANCE * count:
                f.add(Q.MISSING)
            d = np.diff(t_u[g])
            if d.size >= 3 and _mad(d) > JITTER_TOLERANCE * expected:
                f.add(Q.JITTER)
        if np.isnan(rows.v[in_win]).any():
            f.add(Q.MISSING)
        if dup_mask[in_win].any():
            f.add(Q.DUPLICATE)
        if ooo_mask[in_win].any():
            f.add(Q.OUT_OF_ORDER)
        if oor_mask[in_win].any():
            f.add(Q.OUT_OF_RANGE)
        vals = rows.v[in_win][~np.isnan(rows.v[in_win])]
        if vals.size:
            level = float(np.median(np.abs(vals)))
            if suspicious(level, previous_level):
                f.add(Q.UNIT_SUSPECT)
            previous_level = level
        if f:
            spans.append(FlaggedSpan(start=_dt(t0), end=_dt(t1), flags=sorted(f)))
            flags |= f

    # gaps: pauses much longer than usual, including before the first and after the last row
    ref_t = np.unique(np.concatenate([reference.t, t_u])) if reference is not None else t_u
    pause = typical_pause(ref_t, expected)
    factor = GAP_FACTOR if expected else EVENT_GAP_FACTOR
    gap_threshold = max(factor * pause, 3600.0) if pause else DEFAULT_GAP_S
    # A pause running into the window starts at the last row before it (from the reference), as long
    # as the window itself still sees more of it than a normal pause; a gap that ended just after the
    # window began belongs to the previous window.
    start, end = window.start.timestamp(), window.end.timestamp()
    first = float(t_u[0]) if t_u.size else end
    if reference is not None and reference.t.size and reference.t.max() < start:
        if first - start > (pause or 0.0):
            start = float(reference.t.max())
    edges = np.concatenate([[start], t_u, [end]])
    pauses = np.diff(edges)
    gap_idx = np.flatnonzero(pauses > gap_threshold)
    for i in gap_idx:
        spans.append(FlaggedSpan(start=_dt(edges[i]), end=_dt(edges[i + 1]), flags=[Q.GAP]))
    if gap_idx.size:
        flags.add(Q.GAP)
    spans.sort(key=lambda s: s.start)

    return DataQualityReport(
        signal_id=signal.signal_id,
        window=window,
        sample_count=n,
        missing_count=missing_by_cadence + null_count,
        duplicate_count=duplicate_count,
        out_of_order_count=int(ooo_mask.sum()),
        gap_count=int(gap_idx.size),
        median_interval_s=median_interval,
        interval_jitter_s=jitter,
        unit_suspect=Q.UNIT_SUSPECT in flags,
        is_simulated=rows.is_simulated,
        flags=sorted(flags),
        expected_interval_s=expected,
        observation_window_count=len(groups),
        largest_gap_s=float(pauses.max()) if pauses.size else None,
        gap_threshold_s=gap_threshold,
        out_of_range_count=int(oor_mask.sum()),
        valid_range=valid_range,
        not_evaluated=sorted(not_evaluated - flags),
        spans=spans,
    )
