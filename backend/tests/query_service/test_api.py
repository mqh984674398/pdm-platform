"""Query service API: roles, binding, bounds, audit, and credential safety (T010)."""

from __future__ import annotations

import json
import threading

import pytest

from app.datasource.query_service.sources import DataSourceRegistry, env_secret
from app.datasource.sql import AdapterError

from ..datasource.conftest import IOTSHARP_LIKE, parse_ts, raw_rows
from .conftest import SECRET_URL_MARKER, Client, by_key_spec

T0 = parse_ts(raw_rows("S13")[0]["ts"])
RUN = "/api/query-templates/telemetry-by-key-range/run"


def window(hours=6):
    from datetime import timedelta

    return {"start": T0.isoformat(), "end": (T0 + timedelta(hours=hours)).isoformat()}


def create(client, **overrides):
    resp = client.post("/api/admin/query-templates", by_key_spec(**overrides), role="admin")
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_sign_in_and_roles_are_required(client):
    assert client.http.get("/api/query-templates").status_code == 401
    for role in ("viewer", "maintenance", "engineer"):
        assert client.post("/api/admin/query-templates", by_key_spec(), role=role).status_code == 403
    assert client.get("/api/admin/audit", role="engineer").status_code == 403
    assert client.get("/api/datasources/iot/schema", role="viewer").status_code == 403


def test_sql_text_is_visible_to_administrators_only(client):
    create(client)
    public = client.get("/api/query-templates").json()
    assert public[0]["template_id"] == "telemetry-by-key-range" and "sql" not in public[0]
    admin = client.get("/api/admin/query-templates", role="admin").json()
    assert admin[0]["sql"].startswith("SELECT") and admin[0]["created_by"] == "u1"


def test_run_returns_bound_rows_in_order(client):
    create(client)
    body = {"parameters": {"device_id": "SIM-S13", "key_name": "M01_BS1_SPD", **window()}}
    res = client.post(RUN, body).json()
    assert res["columns"] == ["deviceid", "keyname", "ts", "value_double"]
    assert res["row_count"] > 0 and not res["truncated"] and res["is_simulated"]
    ts = [r[2] for r in res["rows"]]
    assert ts == sorted(ts) and all(t.endswith("Z") for t in ts)
    assert {r[1] for r in res["rows"]} == {"M01_BS1_SPD"}


def test_row_limit_truncates_and_says_so(client):
    create(client, max_rows=10)
    body = {"parameters": {"device_id": "SIM-S13", "key_name": "M01_BS1_SPD", **window()}}
    res = client.post(RUN, body).json()
    assert res["row_count"] == 10 and res["truncated"] is True


@pytest.mark.parametrize(
    "params, code",
    [
        ({"device_id": "SIM-S13", "key_name": "M01_BS1_SPD", **window(), "extra": 1}, "invalid_parameter"),
        ({"device_id": "SIM-S13", **window()}, "invalid_parameter"),
        ({"device_id": "SIM-S13' OR '1'='1", "key_name": "M01_BS1_SPD", **window()}, "invalid_parameter"),
        (
            {"device_id": "SIM-S13", "key_name": "M01_BS1_SPD; DROP TABLE telemetrydata", **window()},
            "invalid_parameter",
        ),
        (
            {
                "device_id": "SIM-S13",
                "key_name": "M01_BS1_SPD",
                "start": "2026-02-02T00:00:00",
                "end": "2026-02-02T01:00:00",
            },
            "invalid_parameter",
        ),
        (
            {"device_id": "SIM-S13", "key_name": "M01_BS1_SPD", "start": "yesterday", "end": "today"},
            "invalid_parameter",
        ),
        ({"device_id": "SIM-S13", "key_name": "M01_BS1_SPD", **window(hours=49)}, "limit_exceeded"),
    ],
)
def test_bad_parameters_are_rejected_before_execution(client, params, code):
    create(client)
    resp = client.post(RUN, {"parameters": params})
    assert resp.status_code == 422 and resp.json()["code"] == code
    assert resp.json()["message"]["zh"] and resp.json()["message"]["en"]


def test_string_parameters_are_bound_not_spliced(client):
    spec = by_key_spec(
        template_id="by-note",
        parameters=[{"name": "note", "type": "STRING", "label": {"zh": "备注", "en": "Note"}}],
        sql="SELECT deviceid FROM telemetrydata WHERE keyname = :note LIMIT 10",
    )
    assert client.post("/api/admin/query-templates", spec, role="admin").status_code == 201
    hostile = "x'; DELETE FROM telemetrydata; --"
    res = client.post("/api/query-templates/by-note/run", {"parameters": {"note": hostile}}).json()
    assert res["row_count"] == 0
    create(client)
    body = {"parameters": {"device_id": "SIM-S13", "key_name": "M01_BS1_SPD", **window()}}
    assert client.post(RUN, body).json()["row_count"] > 0  # table intact


def test_unsafe_template_is_rejected_and_not_stored(client):
    resp = client.post(
        "/api/admin/query-templates",
        by_key_spec(sql="SELECT * FROM telemetrydata LIMIT 1; DROP TABLE telemetrydata"),
        role="admin",
    )
    assert resp.status_code == 422 and resp.json()["code"] == "template_sql_rejected"
    assert client.get("/api/admin/query-templates", role="admin").json() == []
    assert client.get("/api/admin/audit", role="admin").json() == []


def test_changes_are_versioned_and_audited(client):
    create(client)
    changed = by_key_spec(max_rows=500)
    resp = client.put("/api/admin/query-templates/telemetry-by-key-range", changed)
    assert resp.status_code == 200 and resp.json()["version"] == 2
    assert client.put("/api/admin/query-templates/telemetry-by-key-range", changed).status_code == 409
    history = client.get("/api/admin/query-templates/telemetry-by-key-range/history", role="admin").json()
    assert [h["version"] for h in history] == [1, 2]
    assert client.delete("/api/admin/query-templates/telemetry-by-key-range").status_code == 204
    assert client.post(RUN, {"parameters": {}}).status_code == 404
    log = client.get("/api/admin/audit", role="admin", params={"object_type": "query_template"}).json()
    assert [e["action"] for e in log] == ["template.create", "template.update", "template.retire"]
    assert log[1]["details"]["changed"] == ["max_rows"] and log[1]["actor"] == "u1"
    assert log[1]["details"]["sql_hash_before"] == log[1]["details"]["sql_hash_after"]


def test_no_endpoint_returns_credentials(client):
    create(client)
    client.http.put("/api/run-mode", json={"mode": "production"}, headers=client.as_("admin"))
    body = {"parameters": {"device_id": "SIM-S13", "key_name": "M01_BS1_SPD", **window()}}
    responses = [
        client.get("/api/datasources"),
        client.get("/api/datasources/iot/metadata"),
        client.get("/api/datasources/iot/schema", role="engineer"),
        client.get("/api/query-templates"),
        client.get("/api/admin/query-templates", role="admin"),
        client.get("/api/admin/audit", role="admin"),
        client.post(RUN, body),
    ]
    for r in responses:
        assert r.status_code == 200, r.text
        assert SECRET_URL_MARKER not in r.text and "sqlite:" not in r.text
    src = responses[0].json()[0]
    assert src["credential_ref"] == "secret://pdm/iot-readonly" and src["read_only"] is True


def test_database_errors_are_not_echoed(client):
    spec = by_key_spec(
        template_id="broken",
        parameters=[],
        sql="SELECT no_such_column FROM telemetrydata LIMIT 1",
    )
    assert client.post("/api/admin/query-templates", spec, role="admin").status_code == 201
    resp = client.post("/api/query-templates/broken/run", {"parameters": {}})
    assert resp.status_code == 502 and resp.json()["code"] == "database_error"
    assert "no_such_column" not in resp.text and "SELECT" not in resp.text


def test_concurrency_limit_returns_busy(make_app):
    application = make_app()
    client = Client(application)
    create(client)
    adapter = application.state.sources.adapter("iot")
    held, release = threading.Event(), threading.Event()

    def hold():
        with adapter.connection():
            held.set()
            release.wait(5)

    t = threading.Thread(target=hold)
    t.start()
    held.wait(5)
    try:
        body = {"parameters": {"device_id": "SIM-S13", "key_name": "M01_BS1_SPD", **window()}}
        resp = client.post(RUN, body)
        assert resp.status_code == 429 and resp.json()["code"] == "source_busy"
    finally:
        release.set()
        t.join()


def test_sources_file_resolves_secrets_server_side(tmp_path, monkeypatch, source_url):
    cfg = {
        "data_source_id": "iot",
        "name": "IoT",
        "kind": "SQL",
        "credential_ref": "secret://pdm/iot-readonly",
        "is_simulated": True,
    }
    path = tmp_path / "sources.json"
    path.write_text(json.dumps([{"config": cfg, "layout": IOTSHARP_LIKE.model_dump()}]), encoding="utf-8")
    monkeypatch.delenv("PDM_SECRET_IOT_READONLY", raising=False)
    with pytest.raises(AdapterError, match="not configured") as err:
        DataSourceRegistry.from_file(path)
    assert "sqlite" not in str(err.value)
    monkeypatch.setenv("PDM_SECRET_IOT_READONLY", source_url)
    reg = DataSourceRegistry.from_file(path)
    assert reg.adapter("iot").discover().devices
    with pytest.raises(AdapterError):
        env_secret("postgres://user:pw@host/db")


@pytest.mark.skipif(not __import__("os").environ.get("PDM_TEST_PG_URL"), reason="PDM_TEST_PG_URL not set")
def test_statement_timeout_returns_504_on_postgres(tmp_path):
    import os

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.db import Base, get_session
    from app.datasource.sql import SqlAdapter
    from app.main import create_app

    from ..datasource.conftest import SIMULATOR_LIKE, seed_simulator_like_pg, source_config

    url = os.environ["PDM_TEST_PG_URL"]
    seed_simulator_like_pg(url, "S13")
    cfg = source_config(data_source_id="iot", statement_timeout_s=1)
    reg = DataSourceRegistry()
    reg.add(cfg, SqlAdapter(cfg, SIMULATOR_LIKE, url))
    engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}")
    Base.metadata.create_all(engine)
    application = create_app(sources=reg)

    def session():
        with sessionmaker(engine)() as s:
            yield s

    application.dependency_overrides[get_session] = session
    client = Client(application)
    spec = by_key_spec(
        template_id="heavy",
        parameters=[],
        sql="SELECT count(*) FROM iot.raw_telemetry a, iot.raw_telemetry b, iot.raw_telemetry c LIMIT 1",
    )
    assert client.post("/api/admin/query-templates", spec, role="admin").status_code == 201
    resp = client.post("/api/query-templates/heavy/run", {"parameters": {}})
    assert resp.status_code == 504 and resp.json()["code"] == "query_timeout"
