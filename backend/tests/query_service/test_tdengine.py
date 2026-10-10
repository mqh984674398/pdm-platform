"""D-035: TDengine sources over the REST API, and the simulation database reserved for administrators.

The TDengine server is faked with an httpx transport that answers the few statements the adapter
sends, in the REST v3 response shape (code, column_meta, data). Nothing here is a live TDengine run.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.main  # noqa: F401  (registers tables)
from app.core.db import Base, get_session
from app.core.schemas import TimeWindow
from app.datasource.query_service.defaults import ensure_standard_templates
from app.datasource.query_service.sources import DataSourceRegistry
from app.datasource.schemas import DataSourceConfig, DataSourceKind
from app.datasource.simulated import SimulatedAdapter
from app.datasource.sql import AdapterError
from app.datasource.tdengine import TdengineAdapter, TdengineLayout, literal, render
from app.main import create_app
from app.simulation.golden import scenario_dir

T0 = datetime(2026, 3, 1, tzinfo=UTC)


class FakeTaos:
    """Answers DESCRIBE / SHOW / SELECT for one wide super table ``meters``."""

    def __init__(self):
        self.statements: list[str] = []
        self.rows = [
            [(T0 + timedelta(seconds=i)).isoformat().replace("+00:00", "Z"), 1.0 + i, 10 * i, "M1"]
            for i in range(5)
        ]

    def ok(self, cols, data):
        return httpx.Response(
            200,
            json={"code": 0, "column_meta": [[c, t, 8] for c, t in cols], "data": data, "rows": len(data)},
        )

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rest/sql/plant"
        assert request.headers["authorization"].startswith("Basic ")
        sql = request.content.decode()
        self.statements.append(sql)
        low = sql.lower()
        if low.startswith("describe"):
            return self.ok(
                [("field", "VARCHAR"), ("type", "VARCHAR"), ("length", "INT"), ("note", "VARCHAR")],
                [["ts", "TIMESTAMP", 8, ""], ["torque", "DOUBLE", 8, ""], ["speed", "INT", 4, ""],
                 ["device_id", "VARCHAR", 32, "TAG"]],
            )  # fmt: skip
        if low.startswith("show stables"):
            return self.ok([("stable_name", "VARCHAR")], [["meters"]])
        if "server_version" in low:
            return self.ok([("server_version()", "VARCHAR")], [["3.3.6.0"]])
        if low.startswith("select distinct"):
            return self.ok([("device_id", "VARCHAR")], [["M1"], ["M2"]])
        if "first(" in low:
            return self.ok(
                [("first(ts)", "TIMESTAMP"), ("last(ts)", "TIMESTAMP")], [[self.rows[0][0], self.rows[-1][0]]]
            )
        if low.startswith("select"):
            if "`torque`" in sql:
                return self.ok([("ts", "TIMESTAMP"), ("torque", "DOUBLE")], [[r[0], r[1]] for r in self.rows])
            return self.ok(
                [("ts", "TIMESTAMP"), ("torque", "DOUBLE"), ("speed", "INT"), ("device_id", "VARCHAR")],
                self.rows,
            )
        return httpx.Response(200, json={"code": 0x2600, "desc": "syntax error"})


def td_config(**kw) -> DataSourceConfig:
    return DataSourceConfig(
        data_source_id="taos-plant",
        name="TDengine plant",
        kind=DataSourceKind.TDENGINE,
        engine="tdengine",
        host="10.0.0.5",
        port=6041,
        database="plant",
        credential_ref="secret://pdm/taos-readonly",
        read_only=True,
        is_simulated=False,
        **kw,
    )


@pytest.fixture
def taos():
    return FakeTaos()


@pytest.fixture
def adapter(taos):
    layout = TdengineLayout(stable="meters", device_tag="device_id")
    return TdengineAdapter(td_config(), layout, "reader:secret", transport=httpx.MockTransport(taos))


def test_wide_layout_discovers_devices_and_numeric_keys(adapter):
    meta = adapter.discover()
    assert [d.device_id for d in meta.devices] == ["M1", "M2"]
    assert meta.devices[0].key_names == ["torque", "speed"]
    assert meta.earliest_ts == T0 and not meta.is_simulated


def test_range_query_is_bounded_and_escaped(adapter, taos):
    rows = adapter.query_range("M1", "torque", TimeWindow(start=T0, end=T0 + timedelta(hours=1)), 100)
    assert [r.value for r in rows] == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert rows[0].ts == T0 and rows[0].source_ref == "taos-plant:meters"
    sql = taos.statements[-1]
    assert "`device_id` = 'M1'" in sql and "LIMIT 100" in sql and sql.startswith("SELECT")
    with pytest.raises(AdapterError):
        adapter.query_range("M1", "pressure", TimeWindow(start=T0, end=T0 + timedelta(hours=1)), 10)


def test_only_read_statements_are_sent(adapter):
    with pytest.raises(AdapterError):
        adapter.sql("DELETE FROM meters")
    with pytest.raises(AdapterError):
        adapter.sql("insert into meters values (now, 1)")


def test_literals_cannot_break_out_of_strings():
    assert literal("a'b") == "'a\\'b'"
    assert literal(T0) == "'2026-03-01T00:00:00.000Z'"
    with pytest.raises(AdapterError):
        literal("x\ny")
    assert (
        render("SELECT * FROM t WHERE d = :d AND s = ':d'", {"d": "M1"})
        == "SELECT * FROM t WHERE d = 'M1' AND s = ':d'"
    )


def test_errors_from_the_server_are_reported(adapter):
    with pytest.raises(AdapterError, match="syntax error"):
        adapter.sql("SHOW nonsense")


def test_registry_loads_tdengine_without_the_production_flag(tmp_path, monkeypatch):
    path = tmp_path / "sources.json"
    item = {
        "config": json.loads(td_config().model_dump_json()),
        "tdengine_layout": {"stable": "meters", "device_tag": "device_id"},
    }
    path.write_text(json.dumps([item]), encoding="utf-8")
    monkeypatch.setenv("PDM_SECRET_TAOS_READONLY", "reader:secret")
    reg = DataSourceRegistry.from_file(path, allow_production=False)
    assert [c.data_source_id for c in reg.configs()] == ["taos-plant"] and reg.skipped == []
    assert isinstance(reg.adapter("taos-plant"), TdengineAdapter)


@pytest.fixture
def client(adapter, tmp_path):
    reg = DataSourceRegistry()
    sim = DataSourceConfig(
        data_source_id="sim-iot", name="sim", kind=DataSourceKind.SIMULATED, read_only=True, is_simulated=True
    )
    reg.add(sim, SimulatedAdapter(scenario_dir("S01"), "sim-iot"))
    reg.add(adapter.config, adapter)
    engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with Session(engine) as s:
        assert "taos-plant-telemetry-by-key-range" in ensure_standard_templates(s, reg)

    def session():
        with factory() as s:
            yield s

    application = create_app(sources=reg)
    application.dependency_overrides[get_session] = session
    return TestClient(application)


def h(role):
    return {"X-PDM-User": "u1", "X-PDM-Role": role}


def test_simulation_database_is_for_administrators_only(client):
    ids = lambda role: [s["data_source_id"] for s in client.get("/api/datasources", headers=h(role)).json()]  # noqa: E731
    assert ids("admin") == ["sim-iot", "taos-plant"]
    assert ids("engineer") == ["taos-plant"] and ids("viewer") == ["taos-plant"]
    r = client.get("/api/datasources/sim-iot/devices", headers=h("engineer"))
    assert r.status_code == 403 and r.json()["code"] == "source_forbidden"
    assert client.get("/api/datasources/sim-iot/devices", headers=h("admin")).status_code == 200
    templates = {t["data_source_id"] for t in client.get("/api/query-templates", headers=h("viewer")).json()}
    assert templates == {"taos-plant"}
    run = client.post(
        "/api/query-templates/telemetry-by-key-range/run", json={"parameters": {}}, headers=h("viewer")
    )
    assert run.status_code == 403


def test_tdengine_template_runs_for_engineers(client):
    body = {"parameters": {"device_id": "M1", "start": "2026-03-01T00:00:00Z", "end": "2026-03-01T01:00:00Z"}}
    r = client.post(
        "/api/query-templates/taos-plant-telemetry-by-key-range/run", json=body, headers=h("engineer")
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["row_count"] == 5 and out["columns"][0] == "ts" and out["is_simulated"] is False
