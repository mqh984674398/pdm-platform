"""Chart-only downsampling (L2-06). Results are for display and never feed algorithms.

Largest-Triangle-Three-Buckets keeps the visual shape (peaks, steps) with far fewer points. Missing
values split a series into segments; segments are downsampled separately and a ``None`` point marks
each gap, so charts show the gap instead of drawing across it.
"""

from __future__ import annotations

from datetime import datetime

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
