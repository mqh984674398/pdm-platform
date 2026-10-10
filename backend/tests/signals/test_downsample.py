"""Chart downsampling (L2-06): shape-preserving, gap-aware, display only."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from app.signals.downsample import lttb, visualization_series
from app.signals.schemas import NormalizedSample

T0 = datetime(2026, 2, 2, tzinfo=UTC)


def samples(values):
    return [
        NormalizedSample(
            signal_id="s",
            ts=T0 + timedelta(seconds=2 * i),
            value=v,
            unit="rpm",
            source_ref="test",
            is_simulated=True,
        )
        for i, v in enumerate(values)
    ]


def test_lttb_keeps_endpoints_size_and_peaks():
    pts = [(float(i), math.sin(i / 20)) for i in range(1000)]
    pts[500] = (500.0, 25.0)  # a spike must survive
    out = lttb(pts, 100)
    assert len(out) == 100 and out[0] == pts[0] and out[-1] == pts[-1]
    assert (500.0, 25.0) in out
    assert [p[0] for p in out] == sorted(p[0] for p in out)
    assert lttb(pts[:10], 100) == pts[:10]


def test_gaps_are_kept_as_none_markers():
    values = [float(i) for i in range(500)] + [None] * 10 + [float(i) for i in range(500)]
    viz = visualization_series("s", "rpm", samples(values), 100, True)
    assert viz.downsampled and viz.source_point_count == 1010
    gaps = [p for p in viz.points if p.value is None]
    assert len(gaps) == 1 and gaps[0].ts == T0 + timedelta(seconds=2 * 510)
    assert len(viz.points) <= 101


def test_short_series_pass_through_unchanged():
    viz = visualization_series("s", "rpm", samples([1.0, None, 3.0]), 100, False)
    assert not viz.downsampled and [p.value for p in viz.points] == [1.0, None, 3.0]
    assert viz.is_simulated is False
