"""T011 AC2: preview returns full-resolution normalized series and downsampled chart series separately."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from .conftest import mapping, signal

S13_WINDOW = {"start": "2026-02-05T00:00:00Z", "end": "2026-02-06T00:00:00Z"}  # 72-96 h: missing torque rows


def body(**kw):
    req = {"mappings": [mapping()], "signals": [signal()], "window": S13_WINDOW, "max_points": 50}
    req.update(kw)
    return req


def adapter_rows(sources, source, device, key, window):
    from app.core.schemas import TimeWindow

    return sources.adapter(source).query_range(device, key, TimeWindow.model_validate(window), 1000)


def test_normalized_and_chart_series_are_separate(client, sources):
    resp = client.post("/api/signals/preview", body())
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["is_simulated"] is True
    (norm,), (viz,) = data["normalized"], data["visualization"]
    raw = adapter_rows(sources, "sim-iot", "SIM-S13", "M01_BS1_SPD", S13_WINDOW)
    assert len(norm["samples"]) == len(raw) > 50 and norm["truncated"] is False
    assert [s["value"] for s in norm["samples"]] == [r.value for r in raw]  # nothing dropped or resampled
    assert norm["samples"][0]["source_ref"] == "sim-iot:S13_missing_duplicate"
    assert viz["downsampled"] is True and viz["method"] == "lttb"
    assert viz["source_point_count"] == len(raw) and len(viz["points"]) <= 50 + 4
    assert viz["points"][0]["ts"] == norm["samples"][0]["ts"]  # LTTB keeps the first point


def test_conversion_and_valid_range_are_applied(client, sources):
    conv = {"source_unit": "rpm", "target_unit": "rad/s", "scale": 0.10471975511965977, "offset": 0.0}
    req = body(mappings=[mapping(conversion=conv)], signals=[signal(unit="rad/s", valid_max=200.0)])
    norm = client.post("/api/signals/preview", req).json()["normalized"][0]
    raw = adapter_rows(sources, "sim-iot", "SIM-S13", "M01_BS1_SPD", S13_WINDOW)
    assert norm["unit"] == "rad/s"
    for s, r in zip(norm["samples"], raw, strict=True):
        assert s["value"] == pytest.approx(r.value * conv["scale"])
        assert ("OUT_OF_RANGE" in s["quality"]) == (s["value"] > 200.0)
    assert any("OUT_OF_RANGE" in s["quality"] for s in norm["samples"])


def test_small_series_are_not_downsampled_and_normalized_can_be_skipped(client):
    data = client.post("/api/signals/preview", body(max_points=10_000, include_normalized=False)).json()
    assert data["normalized"] == []
    assert data["visualization"][0]["downsampled"] is False and data["visualization"][0]["method"] is None


def test_preview_works_on_sql_sources(client, sources):
    req = body(
        mappings=[mapping(source="iot", key="M01_BS1_TRQ", unit="N*m", signal_id="t")],
        signals=[signal("t", unit="N*m")],
    )
    data = client.post("/api/signals/preview", req).json()
    raw = adapter_rows(sources, "iot", "SIM-S13", "M01_BS1_TRQ", S13_WINDOW)
    assert len(data["normalized"][0]["samples"]) == len(raw) > 0
    assert data["normalized"][0]["samples"][0]["source_ref"].startswith("iot:")


def test_rows_beyond_the_source_limit_are_truncated(client, sources):
    long_window = {"start": "2026-02-02T00:00:00Z", "end": "2026-02-09T00:00:00Z"}
    req = body(mappings=[mapping(source="iot")], window=long_window)  # iot max_rows=1000
    norm = client.post("/api/signals/preview", req).json()["normalized"][0]
    assert norm["truncated"] is True and len(norm["samples"]) == 999


def test_saved_definitions_are_used_and_unknown_signals_rejected(client):
    assert client.post("/api/signals/preview", body(signals=[])).status_code == 404
    client.put("/api/signal-config/signals/M01-BS1.speed", {"item": signal()}, role="engineer")
    assert client.post("/api/signals/preview", body(signals=[])).status_code == 200


def test_saved_signal_preview(client):
    client.put("/api/signal-config/signals/M01-BS1.speed", {"item": signal()}, role="engineer")
    url = "/api/signals/M01-BS1.speed/preview"
    q = {"start": S13_WINDOW["start"], "end": S13_WINDOW["end"], "max_points": 20}
    assert client.get(url, params=q).status_code == 404  # no mapping yet
    client.put("/api/signal-config/mappings/M01-BS1.speed", {"item": mapping()}, role="engineer")
    data = client.get(url, params=q).json()
    assert data["visualization"][0]["signal_id"] == "M01-BS1.speed" and len(data["normalized"]) == 1


def test_bounds(client):
    start = datetime(2026, 2, 2, tzinfo=UTC)
    too_long = {"start": start.isoformat(), "end": (start + timedelta(hours=169)).isoformat()}
    resp = client.post("/api/signals/preview", body(window=too_long))
    assert resp.status_code == 422 and resp.json()["code"] == "limit_exceeded"
    assert client.post("/api/signals/preview", body(max_points=5)).status_code == 422
    assert client.post("/api/signals/preview", body(mappings=[mapping()] * 33)).status_code == 422
    bad_unit = body(mappings=[mapping(unit="N*m")])
    assert client.post("/api/signals/preview", bad_unit).json()["code"] == "invalid_preview"
    assert client.post("/api/signals/preview", body(mappings=[mapping(source="nope")])).status_code == 404
    assert client.http.post("/api/signals/preview", json=body()).status_code == 401
