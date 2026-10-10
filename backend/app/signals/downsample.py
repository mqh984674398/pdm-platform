"""Chart-only downsampling (L2-06). Results are for display and never feed algorithms.

Largest-Triangle-Three-Buckets keeps the visual shape (peaks, steps) with far fewer points. Missing
values split a series into segments; segments are downsampled separately and a ``None`` point marks
each gap, so charts show the gap instead of drawing across it.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np

from app.signals.schemas import NormalizedSample, SeriesPoint, VisualizationSeries

Point = tuple[float, float]  # (epoch seconds, value)


def lttb(points: list[Point], threshold: int) -> list[Point]:
    n = len(points)
    if threshold >= n:
        return list(points)
    if threshold < 3:
        return [points[0], points[-1]]
    out = [points[0]]
    bucket = (n - 2) / (threshold - 2)
    a = 0
    for i in range(threshold - 2):
        start, end = int(i * bucket) + 1, int((i + 1) * bucket) + 1
        nxt_start, nxt_end = end, min(int((i + 2) * bucket) + 1, n)
        nxt = points[nxt_start:nxt_end] or [points[-1]]
        avg_x = sum(p[0] for p in nxt) / len(nxt)
        avg_y = sum(p[1] for p in nxt) / len(nxt)
        ax, ay = points[a]
        best, best_area = start, -1.0
        for j in range(start, min(end, n - 1)):
            x, y = points[j]
            area = abs((ax - avg_x) * (y - ay) - (ax - x) * (avg_y - ay))
            if area > best_area:
                best, best_area = j, area
        out.append(points[best])
        a = best
    out.append(points[-1])
    return out


def _segments(samples: list[NormalizedSample]) -> list[list[NormalizedSample]]:
    segs: list[list[NormalizedSample]] = [[]]
    for s in samples:
        if s.value is None:
            if segs[-1]:
                segs.append([])
        else:
            segs[-1].append(s)
    return [seg for seg in segs if seg]


def visualization_series(
    signal_id: str, unit: str, samples: list[NormalizedSample], max_points: int, is_simulated: bool
) -> VisualizationSeries:
    valid = sum(1 for s in samples if s.value is not None)
    if len(samples) <= max_points:
        points = [SeriesPoint(ts=s.ts, value=s.value) for s in samples]
        return VisualizationSeries(
            signal_id=signal_id,
            unit=unit,
            points=points,
            downsampled=False,
            source_point_count=len(samples),
            method=None,
            is_simulated=is_simulated,
        )
    segs = _segments(samples)
    budget = max_points - (len(segs) - 1)  # one gap marker between segments
    points: list[SeriesPoint] = []
    zone = samples[0].ts.tzinfo
    for k, seg in enumerate(segs):
        share = max(2, round(budget * len(seg) / valid)) if valid else 2
        raw = [(s.ts.timestamp(), s.value) for s in seg]
        if k:
            points.append(SeriesPoint(ts=seg[0].ts, value=None))
        points += [
            SeriesPoint(ts=datetime.fromtimestamp(x, zone), value=y)
            for x, y in lttb(raw, min(share, len(raw)))  # type: ignore[arg-type]
        ]
    return VisualizationSeries(
        signal_id=signal_id,
        unit=unit,
        points=points,
        downsampled=True,
        source_point_count=len(samples),
        method="lttb",
        is_simulated=is_simulated,
    )


GAP_FACTOR = 5.0  # a pause longer than this many median intervals is drawn as a gap


def minmax(t: np.ndarray, v: np.ndarray, max_points: int) -> tuple[np.ndarray, np.ndarray, bool]:
    """Fast chart downsampling for large series (L2-06): per bucket the minimum and the maximum, in
    time order, so peaks survive. Pauses longer than ``GAP_FACTOR`` median intervals and missing values
    become a nan point, so the chart shows a gap. Returns (t, v, downsampled)."""
    ok = ~np.isnan(v)
    t, v = t[ok], v[ok]
    n = t.size
    if n <= max_points:
        tg, vg = _with_gaps(t, v)
        return tg, vg, False
    dt = np.diff(t)
    thr = GAP_FACTOR * float(np.median(dt)) if dt.size else np.inf
    cuts = np.flatnonzero(dt > thr) + 1
    bounds = np.concatenate(([0], cuts, [n]))
    segs = len(bounds) - 1
    budget = max(max_points - segs, 2 * segs)
    out_t: list[np.ndarray] = []
    out_v: list[np.ndarray] = []
    for a, b in zip(bounds[:-1], bounds[1:], strict=True):
        if out_t:
            out_t.append(np.array([t[a - 1] + (t[a] - t[a - 1]) / 2]))
            out_v.append(np.array([np.nan]))
        k = max(1, int(budget * (b - a) / n) // 2)
        if b - a <= 2 * k:
            out_t.append(t[a:b])
            out_v.append(v[a:b])
            continue
        edges = np.linspace(a, b, k + 1).astype(int)
        for lo, hi in zip(edges[:-1], edges[1:], strict=True):
            seg = v[lo:hi]
            i, j = lo + int(np.argmin(seg)), lo + int(np.argmax(seg))
            idx = [i, j] if i <= j else [j, i]
            if i == j:
                idx = [i]
            out_t.append(t[idx])
            out_v.append(v[idx])
    return np.concatenate(out_t), np.concatenate(out_v), True


def _with_gaps(t: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if t.size < 3:
        return t, v
    dt = np.diff(t)
    gaps = np.flatnonzero(dt > GAP_FACTOR * float(np.median(dt)))
    if not gaps.size:
        return t, v
    return np.insert(t, gaps + 1, t[gaps] + dt[gaps] / 2), np.insert(v, gaps + 1, np.nan)
