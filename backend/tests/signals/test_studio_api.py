"""Studio support endpoints (UI-04) over the simulated source and a SQL source."""

from __future__ import annotations

import json

import pytest

from app.datasource.query_service.sources import DataSourceRegistry
from app.datasource.simulated import SimulatedAdapter

from .conftest import DATA, STUDIO_SOURCES, mapping, signal

ENG = "engineer"


def test_connection_checks(client):
    for src in ("sim-iot", "iot"):
        checks = client.get(f"/api/datasources/{src}/check", role=ENG).json()
        assert [(c["key"], c["ok"]) for c in checks] == [
            ("reachable", True),
            ("readOnly", True),
            ("timeout", True),
            ("rowLimit", True),
        ]
    assert client.get("/api/datasources/sim-iot/check").status_code == 403  # viewer


def test_layout_of_simulated_and_sql_sources(client):
    sim = client.get("/api/datasources/sim-iot/layout", role=ENG).json()
    assert sim["table"] == "raw_telemetry" and sim["row_count"] > 0 and sim["is_simulated"]
    assert {c["name"]: c["role"] for c in sim["columns"]}["value_double"] == "value"
    assert len(sim["sample_rows"]) == 5 and sim["sample_rows"][0][0] == "SIM-S01"
    sql = client.get("/api/datasources/iot/layout", role=ENG).json()
    roles = {c["name"]: c["role"] for c in sql["columns"]}
    assert roles == {
        "id": None,
        "deviceid": "device",
        "keyname": "key",
        "datetime": "time",
        "value_double": "value",
        "value_long": "value",
    }
    assert sql["row_count"] is None and len(sql["sample_rows"]) == 5
    assert "secret" not in json.dumps(sql).lower()


def test_devices_with_labels_and_row_counts(client):
    devices = {d["device_id"]: d for d in client.get("/api/datasources/sim-iot/devices").json()}
    assert sorted(devices) == ["SIM-S01", "SIM-S13", "SIM-S14", "SIM-S16"]
    s13 = devices["SIM-S13"]
    assert s13["dataset_id"] == "S13" and s13["label"]["en"]
    assert {k["key_name"]: k["rows"] for k in s13["keys"]}["M01_BS1_TRQ"] == 1533  # after injected loss
    sql = client.get("/api/datasources/iot/devices").json()
    assert sql[0]["label"] is None and sql[0]["keys"][0]["rows"] is None


def test_suggestions_from_simulator_topology(client):
    s = client.get("/api/datasources/sim-iot/devices/SIM-S13/suggestions").json()
    assert {m["key_name"] for m in s["mappings"]} == {
        "M01_BS1_SPD",
        "M01_BS1_TRQ",
        "M01_CY1_EXT",
        "M01_CY1_RET",
    }
    assert all(m["data_source_id"] == "sim-iot" for m in s["mappings"])
    assert {c["component_id"] for c in s["components"]} == {"M01-BS1", "M01-CY1"}
    assert s["preview_window"] == {"start": "2026-02-05T00:00:00Z", "end": "2026-02-06T00:00:00Z"}


def test_saved_configuration_wins_over_topology(client):
    sid = "SIM-S13.spd"
    client.put("/api/signal-config/signals/" + sid, {"item": signal(sid)}, role=ENG)
    client.put("/api/signal-config/mappings/" + sid, {"item": mapping(sid)}, role=ENG)
    s = client.get("/api/datasources/sim-iot/devices/SIM-S13/suggestions").json()
    by_key = {m["key_name"]: m["signal_id"] for m in s["mappings"]}
    assert by_key["M01_BS1_SPD"] == sid and len(by_key) == 4
    assert {x["signal_id"] for x in s["signals"]} == set(by_key.values())


def test_sql_source_suggestions_and_unknown_device(client):
    s = client.get("/api/datasources/iot/devices/SIM-S13/suggestions").json()
    assert s["mappings"] == [] and s["components"] == [] and s["preview_window"]["end"]
    resp = client.get("/api/datasources/iot/devices/NOPE/suggestions")
    assert resp.status_code == 404 and resp.json()["code"] == "unknown_device"


def test_sources_file_builds_one_source_from_several_datasets():
    reg = DataSourceRegistry.from_file(STUDIO_SOURCES)
    adapter = reg.adapter("sim-iot")
    assert isinstance(adapter, SimulatedAdapter) and len(adapter.dataset_dirs) == 4
    assert reg.dataset_for("sim-iot", "SIM-S16").dataset_id == "S16"
    assert reg.dataset_for("sim-iot", "SIM-S02") is None


def test_overlapping_datasets_are_refused():
    s13 = next((DATA / "scenarios").glob("S13_*"))
    with pytest.raises(ValueError, match="more than one dataset"):
        SimulatedAdapter([s13, s13])
