"""Speed/torque alignment (L4-02).

Samples are paired by nearest timestamp within a tolerance. Inside each observation window with real
motion, the two signals must tell the same story: a clearly moving axis has torque away from its
standstill level, and an axis at rest (speed within its noise) has no motion torque. When the share
of samples that disagree is high, the window is MISALIGNED: one signal is shifted in time against the
other, so features combining them (torque at speed, efficiency) would be wrong.

The torque at standstill is also compared with its level over the reference period: a shift there
points to sensor bias (BIAS_SUSPECT), which is reported and never corrected.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

from app.core.schemas import TimeWindow
from app.monitoring.quality.assess import Rows, observation_windows
from app.monitoring.schemas import AlignmentReport
from app.signals.schemas import QualityFlag

Q = QualityFlag
MIN_AGREEMENT = 0.8  # aligned data stays above ~0.88 even when sampling aliases with the motion cycle
MIN_PAIRS = 10
BIAS_MAD_FACTOR = 3.0
BIAS_MIN_SHARE = 0.05  # of the typical motion torque, so tiny shifts on a quiet axis are ignored


def _mad(x: np.ndarray) -> float:
    return float(1.4826 * np.median(np.abs(x - np.median(x)))) if x.size else 0.0


def pair(speed: Rows, torque: Rows, tolerance_s: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Indices (speed, torque) of nearest-timestamp pairs within tolerance, and their |Δt|."""
    ok_t = np.flatnonzero(~np.isnan(torque.v))
    tt = torque.t[ok_t]
    if tt.size == 0 or speed.t.size == 0:
        return np.array([], int), np.array([], int), np.array([])
    pos = (
        np.clip(np.searchsorted(tt, speed.t), 1, tt.size - 1) if tt.size > 1 else np.zeros(speed.t.size, int)
    )
    left = np.where(pos > 0, pos - 1, 0)
    choose = np.where(np.abs(tt[left] - speed.t) <= np.abs(tt[pos] - speed.t), left, pos)
    dt = np.abs(tt[choose] - speed.t)
    keep = (dt <= tolerance_s) & ~np.isnan(speed.v)
    return np.flatnonzero(keep), ok_t[choose[keep]], dt[keep]


def window_state(v: np.ndarray, q: np.ndarray) -> tuple[float, float] | None:
    """(agreement, standstill torque) for one observation window, or None without real motion."""
    av = np.abs(v)
    p95 = float(np.percentile(av, 95))
    low = av < 0.02 * p95
    floor = np.sort(av)[: max(3, int(0.3 * av.size))]
    noise_floor = max(float(np.sqrt(np.mean(floor**2))), 1e-9)
    if low.sum() < 5 or p95 < 50 * noise_floor:
        return None  # idle or stopped: nothing to compare
    stand = float(np.median(q[low]))
    dev = np.abs(q - stand)
    big = float(np.percentile(dev, 95))
    if big <= 0:
        return None
    torque_rest, torque_moving = dev < 0.1 * big, dev > 0.5 * big
    rest_speeds = v[torque_rest] if torque_rest.sum() >= 5 else v[low]
    speed_noise = max(_mad(rest_speeds), 1e-9)
    moving_at_rest_torque = (av > 0.1 * p95) & torque_rest
    resting_with_motion_torque = (av < 2 * speed_noise) & torque_moving
    disagree = moving_at_rest_torque | resting_with_motion_torque
    return 1.0 - float(disagree.mean()), stand


def _windows(speed: Rows, torque: Rows, tolerance_s: float, expected_s: float | None):
    si, ti, dt = pair(speed, torque, tolerance_s)
    t = speed.t[si]
    groups = observation_windows(t, expected_s)
    out = []
    for g in groups:
        if g.size < MIN_PAIRS:
            continue
        state = window_state(speed.v[si][g], torque.v[ti][g])
        if state:
            out.append((float(t[g[0]]), float(t[g[-1]]), *state))
    return si, ti, dt, out


def check_pair(
    speed_id: str,
    torque_id: str,
    speed: Rows,
    torque: Rows,
    window: TimeWindow,
    tolerance_s: float,
    expected_s: float | None,
    reference: tuple[Rows, Rows] | None = None,
) -> AlignmentReport:
    si, ti, dt, wins = _windows(speed, torque, tolerance_s, expected_s)
    flags: set[QualityFlag] = set()
    not_evaluated: set[QualityFlag] = set()
    misaligned = [
        TimeWindow(start=datetime.fromtimestamp(a, UTC), end=datetime.fromtimestamp(max(b, a + 1), UTC))
        for a, b, agree, _ in wins
        if agree < MIN_AGREEMENT
    ]
    if misaligned:
        flags.add(Q.MISALIGNED)
    if not wins:
        not_evaluated.add(Q.MISALIGNED)

    stand = float(np.median([w[3] for w in wins])) if wins else None
    ref_stand = None
    if reference is not None:
        _, _, _, ref_wins = _windows(*reference, tolerance_s, expected_s)
        ref_levels = np.array([w[3] for w in ref_wins])
        if ref_levels.size >= 3 and stand is not None:
            ref_stand = float(np.median(ref_levels))
            motion = float(np.percentile(np.abs(torque.v[ti] - stand), 95)) if ti.size else 0.0
            limit = max(BIAS_MAD_FACTOR * _mad(ref_levels), BIAS_MIN_SHARE * motion)
            if abs(stand - ref_stand) > limit:
                flags.add(Q.BIAS_SUSPECT)
    if ref_stand is None:
        not_evaluated.add(Q.BIAS_SUSPECT)

    unpaired_t = int((~np.isnan(torque.v)).sum()) - int(np.unique(ti).size)
    return AlignmentReport(
        speed_signal_id=speed_id,
        torque_signal_id=torque_id,
        window=window,
        tolerance_s=tolerance_s,
        paired_count=int(si.size),
        unpaired_speed_count=int(speed.t.size - si.size),
        unpaired_torque_count=max(unpaired_t, 0),
        median_time_offset_s=float(np.median(dt)) if dt.size else None,
        evaluated_windows=len(wins),
        agreement=min(w[2] for w in wins) if wins else None,
        min_agreement=MIN_AGREEMENT,
        misaligned_windows=misaligned,
        standstill_torque=stand,
        reference_standstill_torque=ref_stand,
        flags=sorted(flags),
        not_evaluated=sorted(not_evaluated),
        is_simulated=speed.is_simulated or torque.is_simulated,
    )
