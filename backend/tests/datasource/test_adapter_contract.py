"""One contract suite for every TimeSeriesAdapter (T009 AC4, L1-07)."""

from __future__ import annotations

from datetime import timedelta

from app.core.schemas import TimeWindow
from app.datasource.adapter import TimeSeriesAdapter

from .conftest import parse_ts, raw_rows


def pairs(rows):
    return sorted((r.ts, r.value) for r in rows)


def first_window(sid: str) -> TimeWindow:
    t0 = parse_ts(raw_rows(sid)[0]["ts"]).replace(hour=0, minute=0, second=0, microsecond=0)
    return TimeWindow(start=t0 + timedelta(days=2), end=t0 + timedelta(days=4))


def test_is_a_time_series_adapter(adapter):
    _, a = adapter
    assert isinstance(a, TimeSeriesAdapter) and a.is_simulated


def test_discovery_matches_source(adapter, reference):
    sid, a = adapter
    meta, ref = a.discover(), reference(sid).discover()
    assert meta.devices == ref.devices
    assert (meta.earliest_ts, meta.latest_ts) == (ref.earliest_ts, ref.latest_ts)
    assert meta.earliest_ts.utcoffset() == timedelta(0)


def test_schema_inspection_lists_columns(adapter):
    _, a = adapter
    schema = a.inspect_schema()
    assert schema.tables and all(t.columns for t in schema.tables)


def test_range_rows_match_reference_in_order(adapter, reference):
    sid, a = adapter
    window = first_window(sid)
    for dk in reference(sid).discover().devices:
        for key in dk.key_names:
            got = a.query_range(dk.device_id, key, window, 100_000)
            ref = reference(sid).query_range(dk.device_id, key, window, 100_000)
            assert pairs(got) == pairs(ref), key
            assert [r.ts for r in got] == sorted(r.ts for r in got)
            assert all(window.start <= r.ts < window.end for r in got)
            assert all(r.source_ref.startswith("test-sql:") and r.is_simulated for r in got)


def test_duplicates_and_out_of_order_rows_are_preserved_and_sorted(adapter):
    sid, a = adapter
    t0 = parse_ts(raw_rows(sid)[0]["ts"])
    window = TimeWindow(start=t0, end=t0 + timedelta(days=7))
    if sid == "S13":  # duplicate rows injected into M01_CY1_EXT
        rows = a.query_range("SIM-S13", "M01_CY1_EXT", window, 100_000)
        ts = [r.ts for r in rows]
        assert len(ts) > len(set(ts))
    else:  # S14 out-of-order arrivals on M01_LM1_SPD come back in time order
        rows = a.query_range("SIM-S14", "M01_LM1_SPD", window, 100_000)
        assert [r.ts for r in rows] == sorted(r.ts for r in rows)


def test_limit_returns_earliest_rows(adapter, reference):
    sid, a = adapter
    window = first_window(sid)
    got = a.query_range(f"SIM-{sid}", "M01_BS1_SPD", window, 25)
    ref = reference(sid).query_range(f"SIM-{sid}", "M01_BS1_SPD", window, 100_000)[:25]
    assert len(got) == 25 and pairs(got) == pairs(ref)


def test_incremental_reads_strictly_after_watermark(adapter):
    sid, a = adapter
    device, key = f"SIM-{sid}", "M01_BS1_SPD"
    start = parse_ts(raw_rows(sid)[0]["ts"]) - timedelta(seconds=1)
    every = a.query_incremental(device, key, start, 200_000)
    collected, mark = [], start
    while batch := a.query_incremental(device, key, mark, 500):
        assert all(r.ts > mark for r in batch)
        collected += batch
        mark = batch[-1].ts
    assert pairs(collected) == pairs(every) and len(every) > 1000


def test_unknown_or_hostile_identifiers_return_nothing(adapter):
    sid, a = adapter
    window = first_window(sid)
    assert a.query_range(f"SIM-{sid}", "NO_SUCH_KEY", window, 10) == []
    assert a.query_range(f"SIM-{sid}' OR '1'='1", "M01_BS1_SPD", window, 10) == []
    assert a.query_range(f"SIM-{sid}", "M01_BS1_SPD'; DROP TABLE telemetrydata; --", window, 10) == []
