"""Operating state from observable evidence (L3-02).

Telemetry arrives in observation windows separated by pauses. Each window gets a state from what its
signals show; the time between windows has no evidence and is UNKNOWN:

- RUNNING: a speed signal shows real motion, or an actuator reported operations.
- IDLE: speed signals report but stay within their noise, and no actuator operated.
- MAINTENANCE: a maintenance record covers the time (records win over telemetry).
- UNKNOWN: no data, only missing values, or nothing that can tell motion from rest.

STOPPED and FAULT need a machine status or alarm signal, which the current sources do not have, so
they are never guessed: a stopped machine that sends nothing reads as UNKNOWN, not STOPPED.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from app.core.schemas import LocalizedText, TimeWindow
from app.datasource.query_service.sources import DataSourceRegistry
from app.equipment.schemas import OperatingState, StateSegment
from app.signals.normalize import convert
from app.signals.schemas import PhysicalQuantity, SignalDefinition, SignalMapping

S = OperatingState
WINDOW_BREAK_MIN_S = 60.0
MOTION_NOISE_FACTOR = 20.0  # 95th percentile speed must exceed this many noise levels
MAX_ROWS = 200_000

NOT_DERIVED = [S.STOPPED, S.FAULT]

REASONS = {
    "motion": LocalizedText(zh="速度信号显示实际运动", en="Speed signals show real motion"),
    "operations": LocalizedText(zh="执行器上报了动作", en="Actuators reported operations"),
    "rest": LocalizedText(
        zh="速度信号在噪声范围内，无执行器动作", en="Speed within noise, no actuator operations"
    ),
    "maintenance": LocalizedText(zh="维护记录覆盖该时段", en="A maintenance record covers this time"),
    "no_data": LocalizedText(
        zh="无数据，无法判断（停机或数据中断）", en="No data: stopped or interrupted, cannot tell"
    ),
    "no_values": LocalizedText(zh="只有缺失值，证据不足", en="Only missing values: insufficient evidence"),
    "no_speed": LocalizedText(
        zh="无速度信号且无执行器动作，无法区分运行与静止", en="No speed signal and no operations: cannot tell"
    ),
}


@dataclass
class Series:
    """One signal in timestamp order: epoch seconds and normalized values (nan = missing)."""

    signal: SignalDefinition
    component_id: str | None
    t: np.ndarray
    v: np.ndarray
    is_simulated: bool

    def between(self, t0: float, t1: float) -> tuple[np.ndarray, np.ndarray]:
        i, j = np.searchsorted(self.t, t0, "left"), np.searchsorted(self.t, t1, "right")
        return self.t[i:j], self.v[i:j]


def load_series(
    sources: DataSourceRegistry,
    items: Sequence[tuple[SignalMapping, SignalDefinition]],
    window: TimeWindow,
) -> list[Series]:
    """Full-resolution rows through the read-only adapters, converted to signal units."""
    out = []
    for m, s in items:
        limit = min(MAX_ROWS, sources.config(m.data_source_id).max_rows)
        rows = sources.adapter(m.data_source_id).query_range(m.device_id, m.key_name, window, limit)
        if len(rows) >= limit:
            raise ValueError(f"more than {limit} rows for '{m.signal_id}'; use a shorter window")
        t = np.array([r.ts.timestamp() for r in rows], dtype=float)
        v = np.array(
            [np.nan if r.value is None else convert(r.value, m.conversion) for r in rows], dtype=float
        )
        order = np.argsort(t, kind="stable")
        sim = any(r.is_simulated for r in rows) or sources.adapter(m.data_source_id).is_simulated
        out.append(Series(s, m.component_id, t[order], v[order], sim))
    return out


def is_speed(s: Series) -> bool:
    return s.signal.quantity == PhysicalQuantity.SPEED


def is_operation(s: Series) -> bool:
    """Event-based duration signals report one value per actuator operation."""
    return s.signal.quantity == PhysicalQuantity.DURATION and s.signal.expected_sampling_s is None


def observation_windows(series: Sequence[Series]) -> list[tuple[float, float]]:
    """Machine-level windows: the union of all timestamps, split at pauses."""
    ts = [s.t for s in series if s.t.size]
    if not ts:
        return []
    t = np.unique(np.concatenate(ts))
    sampled = [s.signal.expected_sampling_s for s in series if s.signal.expected_sampling_s]
    brk = max(WINDOW_BREAK_MIN_S, 30 * min(sampled)) if sampled else WINDOW_BREAK_MIN_S
    cuts = np.flatnonzero(np.diff(t) > brk) + 1
    return [(float(g[0]), float(g[-1])) for g in np.split(t, cuts)]


def moving(v: np.ndarray) -> bool | None:
    """Whether a speed series shows real motion; None when there are too few values to tell."""
    v = np.abs(v[~np.isnan(v)])
    if v.size < 5:
        return None
    p95 = float(np.percentile(v, 95))
    floor = np.sort(v)[: max(3, int(0.3 * v.size))]
    floor_rms = float(np.sqrt(np.mean(floor**2)))
    d = np.diff(v)
    diff_noise = float(1.4826 * np.median(np.abs(d - np.median(d)))) / np.sqrt(2)
    noise = max(min(floor_rms, diff_noise), 1e-9)
    return bool(p95 > MOTION_NOISE_FACTOR * noise)


def window_state(series: Sequence[Series], t0: float, t1: float) -> tuple[OperatingState, list[str], str]:
    """State of one observation window, with the signals that evidence it."""
    speeds, ops = [s for s in series if is_speed(s)], [s for s in series if is_operation(s)]
    moving_ids, rest_ids, any_values = [], [], False
    for s in speeds:
        _, v = s.between(t0, t1)
        any_values |= bool((~np.isnan(v)).any())
        m = moving(v)
        if m is True:
            moving_ids.append(s.signal.signal_id)
        elif m is False:
            rest_ids.append(s.signal.signal_id)
    op_ids = []
    for s in ops:
        _, v = s.between(t0, t1)
        if (~np.isnan(v)).any():
            op_ids.append(s.signal.signal_id)
            any_values = True
    if moving_ids:
        return S.RUNNING, moving_ids + op_ids, "motion"
    if op_ids:
        return S.RUNNING, op_ids, "operations"
    if rest_ids:
        return S.IDLE, rest_ids, "rest"
    if not any_values:
        return S.UNKNOWN, [], "no_values"
    return S.UNKNOWN, [], "no_speed"


def _dt(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, UTC)


def derive_states(
    series: Sequence[Series],
    window: TimeWindow,
    maintenance: Sequence[tuple[datetime, datetime, str]] = (),
) -> list[StateSegment]:
    """State segments covering ``window`` end to end. ``maintenance``: (start, end, record id)."""
    start, end = window.start.timestamp(), window.end.timestamp()
    sim = any(s.is_simulated for s in series)
    marks: list[tuple[float, float, OperatingState, list[str], str]] = []
    for t0, t1 in observation_windows(series):
        state, evidence, why = window_state(series, t0, t1)
        marks.append((t0, max(t1, t0 + 1e-3), state, evidence, why))

    # maintenance records override telemetry where they overlap
    maint: list[tuple[float, float, list[str]]] = []
    for a, b, rid in sorted((a.timestamp(), b.timestamp(), rid) for a, b, rid in maintenance):
        if maint and a <= maint[-1][1]:
            maint[-1] = (maint[-1][0], max(maint[-1][1], b), [*maint[-1][2], rid])
        else:
            maint.append((a, b, [rid]))
    timeline: list[tuple[float, float, OperatingState, list[str], str]] = []
    for a, b, st, ev, why in marks:
        pieces = [(a, b)]
        for ma, mb, _ in maint:
            pieces = [p for x, y in pieces for p in ((x, min(y, ma)), (max(x, mb), y)) if p[1] > p[0]]
        timeline += [(x, y, st, ev, why) for x, y in pieces]
    timeline += [(max(ma, start), min(mb, end), S.MAINTENANCE, ids, "maintenance") for ma, mb, ids in maint]
    timeline = sorted(p for p in timeline if p[1] > start and p[0] < end)

    out: list[StateSegment] = []
    cursor = start
    for a, b, st, ev, why in timeline:
        a, b = max(a, start), min(b, end)
        if a > cursor:
            out.append(_segment(cursor, a, S.UNKNOWN, [], "no_data", sim))
        out.append(_segment(a, b, st, ev, why, sim))
        cursor = max(cursor, b)
    if cursor < end:
        out.append(_segment(cursor, end, S.UNKNOWN, [], "no_data", sim))
    return out


def _segment(a: float, b: float, st: OperatingState, ev: list[str], why: str, sim: bool) -> StateSegment:
    return StateSegment(
        start=_dt(a), end=_dt(b), state=st, evidence=ev, reason=REASONS[why], is_simulated=sim
    )


def state_at(segments: Sequence[StateSegment], ts: datetime) -> OperatingState:
    for seg in segments:
        if seg.start <= ts <= seg.end:
            return seg.state
    return S.UNKNOWN
