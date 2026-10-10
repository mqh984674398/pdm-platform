"""T019: server-side chart downsampling and full-resolution export (SIMULATED data)."""

import time
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.core.audit  # noqa: F401
import app.signals.registry  # noqa: F401
from app.core.db import Base, get_session
from app.core.schemas import TimeWindow
from app.datasource.adapter import TimeSeriesAdapter
from app.datasource.query_service.sources import DataSourceRegistry
from app.datasource.schemas import DataSourceConfig, DataSourceKind, RawTelemetryRow
from app.datasource.simulated import SimulatedAdapter
from app.main import create_app
from app.signals.downsample import minmax

from ..equipment.conftest import scenario
from ..query_service.conftest import Client

T0 = datetime(2026, 1, 1, tzinfo=UTC)
N = 1_200_000


class ArrayAdapter(TimeSeriesAdapter):
    """In-memory SIMULATED source with one dense key (1 s), for timing the endpoint."""

    data_source_id, is_simulated = "bench", True

    def __init__(self):
        rng = np.random.default_rng(1)
        self.t = T0.timestamp() + np.arange(N, dtype=float)
        self.v = np.sin(np.arange(N) / 500) + rng.normal(0, 0.01, N)
        self.v[600_000] = 9.0  # one spike
        self.v[700_000:700_010] = np.nan  # missing values

    def query_arrays(self, device_id, key_name, window, limit):
        lo = np.searchsorted(self.t, window.start.timestamp())
        hi = min(np.searchsorted(self.t, window.end.timestamp()), lo + limit)
        return self.t[lo:hi], self.v[lo:hi]

    def query_range(self, device_id, key_name, window, limit):
        t, v = self.query_arrays(device_id, key_name, window, limit)
        return [
            RawTelemetryRow(
                device_id=device_id,
                key_name=key_name,
                ts=datetime.fromtimestamp(a, UTC),
                value=None if np.isnan(b) else b,
                source_ref="bench",
                is_simulated=True,
            )
            for a, b in zip(t, v, strict=True)
        ]

    def discover(self):
        from app.datasource.schemas import SourceMetadata

        return SourceMetadata(
            data_source_id="bench",
            devices=[],
            earliest_ts=T0,
            latest_ts=datetime.fromtimestamp(self.t[-1], UTC),
            is_simulated=True,
        )

    def inspect_schema(self):
        raise NotImplementedError

    def query_incremental(self, device_id, key_name, since, limit):
        raise NotImplementedError


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ts.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    def session():
        with factory() as s:
            yield s

    reg = DataSourceRegistry()
    cfg = DataSourceConfig(
        data_source_id="bench",
        name="bench",
        kind=DataSourceKind.SIMULATED,
        read_only=True,
        is_simulated=True,
        max_rows=2_000_000,
    )
    reg.add(cfg, ArrayAdapter())
    app = create_app(sources=reg)
    app.dependency_overrides[get_session] = session
    c = Client(app)
    body = {
        "comment": "bench",
        "signals": [
            {
                "signal_id": "B.torque",
                "name": {"zh": "扭矩", "en": "Torque"},
                "quantity": "TORQUE",
                "unit": "Nm",
                "expected_sampling_s": 1.0,
            }
        ],
        "mappings": [
            {
                "signal_id": "B.torque",
                "data_source_id": "bench",
                "template_id": "t",
                "device_id": "D",
                "key_name": "K",
                "time_field": "ts",
                "value_field": "v",
                "conversion": {"source_unit": "Nm", "target_unit": "Nm", "scale": 2.0, "offset": 0.0},
            }
        ],
    }
    r = c.put("/api/signal-config/sources/bench/devices/D", body, role="engineer")
    assert r.status_code == 200, r.text
    return c


def _q(start, end, **kw):
    return {"start": start.isoformat(), "end": end.isoformat(), **kw}


def test_million_points_are_downsampled_on_the_server(client):
    t = time.perf_counter()
    r = client.get("/api/timeseries/B.torque", params=_q(T0, T0 + timedelta(seconds=N), max_points=2000))
    took = time.perf_counter() - t
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["downsampled"] and d["method"] == "minmax" and d["is_simulated"]
    assert d["source_point_count"] == N - 10
    assert len(d["points"]) <= 2000 + 2
    values = [p["value"] for p in d["points"] if p["value"] is not None]
    assert max(values) == pytest.approx(18.0)  # the spike survives, in signal units (scale 2)
    assert took < 3.0, f"{took:.2f} s"


def test_zoomed_range_is_full_resolution(client):
    r = client.get(
        "/api/timeseries/B.torque", params=_q(T0 + timedelta(seconds=1000), T0 + timedelta(seconds=1500))
    )
    d = r.json()
    assert not d["downsampled"] and d["source_point_count"] == 500 and len(d["points"]) == 500


def test_export_is_full_resolution_and_audited(client):
    r = client.get("/api/timeseries/B.torque/export", params=_q(T0, T0 + timedelta(seconds=50_000)))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "SIMULATED" in r.headers["content-disposition"]
    lines = r.text.strip().split("\n")
    assert lines[0] == "ts,value_Nm,is_simulated" and len(lines) == 50_001
    assert lines[1].startswith("2026-01-01T00:00:00Z,") and lines[1].endswith(",true")
    audit = client.get("/api/admin/audit", role="admin").json()
    rows = audit["items"] if isinstance(audit, dict) else audit
    assert any(a["action"] == "timeseries.export" and a["details"]["rows"] == 50_000 for a in rows)


def test_bounds(client):
    too_long = client.get("/api/timeseries/B.torque", params=_q(T0, T0 + timedelta(days=400)))
    assert too_long.status_code == 422
    assert client.get("/api/timeseries/nope", params=_q(T0, T0 + timedelta(hours=1))).status_code == 404
    assert (
        client.get(
            "/api/timeseries/B.torque", params=_q(T0, T0 + timedelta(hours=1), max_points=5)
        ).status_code
        == 422
    )


def test_minmax_keeps_extremes_and_gaps():
    t = np.arange(10_000, dtype=float)
    v = np.zeros(10_000)
    v[1234], v[8000] = 5.0, -4.0
    t[5000:] += 1000  # a pause
    tt, vv, down = minmax(t, v, 200)
    assert down and tt.size <= 202 and np.all(np.diff(tt) > 0)
    assert np.nanmax(vv) == 5.0 and np.nanmin(vv) == -4.0
    assert np.isnan(vv).sum() == 1  # the pause is a gap
    small_t, small_v, small_down = minmax(t[:100], v[:100], 200)
    assert not small_down and small_t.size == 100


def test_simulated_adapter_arrays_match_rows():
    sc = scenario("S01")
    adapter = sc.sources.adapter("simulated")
    w = TimeWindow(start=sc.t0, end=sc.t0 + timedelta(hours=30))
    rows = adapter.query_range("SIM-S01", "M01_BS1_TRQ", w, 5000)
    t, v = adapter.query_arrays("SIM-S01", "M01_BS1_TRQ", w, 5000)
    assert isinstance(adapter, SimulatedAdapter) and len(rows) == t.size > 0
    assert t.tolist() == [r.ts.timestamp() for r in rows]
    assert [None if np.isnan(x) else x for x in v.tolist()] == [r.value for r in rows]


def test_bench_dataset_is_readable(tmp_path):
    from app.simulation.bench import DEVICE, KEY, START, write_bench_dataset

    write_bench_dataset(tmp_path / "bench", rows=5000)
    a = SimulatedAdapter(tmp_path / "bench", "sim-bench")
    t, v = a.query_arrays(DEVICE, KEY, TimeWindow(start=START, end=START + timedelta(days=1)), 10_000)
    assert t.size == 5000 and np.all(np.diff(t) == 1.0)


def test_extent(client):
    r = client.get("/api/timeseries/B.torque/extent").json()
    assert r["start"].startswith("2026-01-01T00:00:00") and r["end"] > r["start"]
