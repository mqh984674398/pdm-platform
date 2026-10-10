"""Quality report endpoint over the Studio sources (simulated) and a SQL source."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base, get_session
from app.datasource.query_service.sources import DataSourceRegistry
from app.datasource.sql import SqlAdapter
from app.main import create_app

from ..datasource.conftest import IOTSHARP_LIKE, seed_iotsharp_like, source_config
from ..query_service.conftest import Client
from ..signals.conftest import STUDIO_SOURCES, mapping, signal

S13_FAULT = {"start": "2026-02-04T00:00:00Z", "end": "2026-02-06T00:00:00Z"}  # 48-96 h


@pytest.fixture(scope="module")
def sql_url(tmp_path_factory):
    url = f"sqlite:///{tmp_path_factory.mktemp('iot') / 'iot.db'}"
    seed_iotsharp_like(url, "S14")
    return url


@pytest.fixture
def client(sql_url, tmp_path):
    reg = DataSourceRegistry()
    sim = DataSourceRegistry.from_file(STUDIO_SOURCES)
    reg.add(sim.config("sim-iot"), sim.adapter("sim-iot"), sim.datasets("sim-iot"))
    for sid, layout in (
        ("iot", IOTSHARP_LIKE),
        ("iot-ordered", IOTSHARP_LIKE.model_copy(update={"arrival_column": "id"})),
    ):
        cfg = source_config(data_source_id=sid, credential_ref="secret://pdm/x")
        reg.add(cfg, SqlAdapter(cfg, layout, sql_url))
    engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    def session():
        with factory() as s:
            yield s

    app = create_app(sources=reg)
    app.dependency_overrides[get_session] = session
    return Client(app)


def trq(**kw):
    conv = {"source_unit": "%rated", "target_unit": "N*m", "scale": 0.1, "offset": 0.0}
    return mapping("M01-BS1.torque", "M01_BS1_TRQ", unit="N*m", conversion=conv, component_id="M01-BS1", **kw)


def spd(**kw):
    return mapping(component_id="M01-BS1", **kw)


DRAFT_SIGNALS = [signal(), signal("M01-BS1.torque", unit="N*m", quantity="TORQUE")]


def test_draft_signals_report_and_auto_pair(client):
    body = {"mappings": [spd(), trq()], "signals": DRAFT_SIGNALS, "window": S13_FAULT}
    data = client.post("/api/quality/report", body).json()
    assert data["is_simulated"] is True
    by_id = {r["signal_id"]: r for r in data["reports"]}
    assert "MISSING" in by_id["M01-BS1.torque"]["flags"] and by_id["M01-BS1.speed"]["flags"] == []
    (pair,) = data["alignment"]
    assert pair["speed_signal_id"] == "M01-BS1.speed" and pair["torque_signal_id"] == "M01-BS1.torque"
    assert pair["flags"] == [] and pair["evaluated_windows"] > 0


def test_full_resolution_rows_are_assessed_not_chart_points(client):
    """AC4: quality works on every row; the chart series of the same window is downsampled separately."""
    body = {"mappings": [spd()], "signals": DRAFT_SIGNALS, "window": S13_FAULT}
    rep = client.post("/api/quality/report", body).json()["reports"][0]
    prev = client.post("/api/signals/preview", {**body, "max_points": 50}).json()
    assert (
        rep["sample_count"]
        == len(prev["normalized"][0]["samples"])
        == prev["visualization"][0]["source_point_count"]
    )
    assert len(prev["visualization"][0]["points"]) < rep["sample_count"]


def test_saved_signals_by_id(client):
    for item in DRAFT_SIGNALS:
        client.put(f"/api/signal-config/signals/{item['signal_id']}", {"item": item}, role="engineer")
    for m in (spd(), trq()):
        client.put(f"/api/signal-config/mappings/{m['signal_id']}", {"item": m}, role="engineer")
    body = {"signal_ids": ["M01-BS1.torque"], "window": S13_FAULT}
    data = client.post("/api/quality/report", body).json()
    assert [r["signal_id"] for r in data["reports"]] == ["M01-BS1.torque"] and data["alignment"] == []


def test_sql_sources_detect_out_of_order_only_with_an_arrival_column(client):
    window = {"start": "2026-02-04T00:00:00Z", "end": "2026-02-07T00:00:00Z"}  # S14 48-120 h
    lm = signal("M01-LM1.speed", unit="mm/s")
    for source, expect in (("iot", None), ("iot-ordered", True)):
        m = mapping("M01-LM1.speed", "M01_LM1_SPD", device="SIM-S14", source=source, unit="mm/s")
        rep = client.post("/api/quality/report", {"mappings": [m], "signals": [lm], "window": window}).json()[
            "reports"
        ][0]
        if expect:
            assert "OUT_OF_ORDER" in rep["flags"] and rep["out_of_order_count"] > 0
        else:
            assert "OUT_OF_ORDER" in rep["not_evaluated"] and rep["out_of_order_count"] == 0


def test_errors_and_roles(client):
    base = {"mappings": [spd()], "signals": DRAFT_SIGNALS, "window": S13_FAULT}
    assert (
        client.post("/api/quality/report", {"window": S13_FAULT}).json()["code"] == "invalid_quality_request"
    )
    assert (
        client.post("/api/quality/report", {"signal_ids": ["nope"], "window": S13_FAULT}).status_code == 404
    )
    long = {**base, "window": {"start": "2026-02-02T00:00:00Z", "end": "2026-02-10T00:00:00Z"}}
    assert client.post("/api/quality/report", long).json()["code"] == "limit_exceeded"
    bad_pair = {**base, "pairs": [{"speed_signal_id": "M01-BS1.speed", "torque_signal_id": "x"}]}
    assert client.post("/api/quality/report", bad_pair).status_code == 422
    assert client.http.post("/api/quality/report", json=base).status_code == 401
