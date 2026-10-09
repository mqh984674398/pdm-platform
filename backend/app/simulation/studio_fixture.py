"""Data Source Studio demo source (T008, T011): four scenarios as one simulated telemetry source.

Two files come out of it. ``studio_sources.json`` configures the backend's simulated source "sim-iot"
(the real Studio API, T011). ``studio_demo.json`` is the same source as a static snapshot for the
frontend's offline mock (unit tests and the G1 demo). The preview windows are chosen so the preview
and quality steps show real simulated behaviour: a clean source (S01), missing and duplicated rows
(S13), timestamp jitter and out-of-order rows (S14), and a unit-scale fault (S16).
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta
from pathlib import Path

from app.core.schemas import LocalizedText
from app.datasource.schemas import (
    DataSourceConfig,
    DataSourceKind,
    DeviceKeys,
    QueryParameter,
    QueryParamType,
    QueryTemplate,
    SourceMetadata,
)
from app.signals.schemas import SignalConfigVersion
from app.simulation.writer import read_text

SOURCE_ID = "sim-iot"
# (scenario, preview start hour, preview hours): windows chosen to contain each scenario's data fault
DEVICES = [("S01", 0.0, 24.0), ("S13", 72.0, 24.0), ("S14", 48.0, 24.0), ("S16", 132.0, 24.0)]
TABLE_COLUMNS = [
    ("deviceid", "varchar(64)", "device"),
    ("keyname", "varchar(64)", "key"),
    ("ts", "timestamptz", "time"),
    ("datatype", "varchar(16)", None),
    ("value_double", "double precision", "value"),
]


def _p(name: str, kind: QueryParamType, zh: str, en: str) -> QueryParameter:
    return QueryParameter(name=name, type=kind, label=LocalizedText(zh=zh, en=en))


TEMPLATES = [
    (
        QueryTemplate(
            template_id="telemetry-by-key-range",
            name=LocalizedText(zh="按信号键查询时间段", en="Signal key over a time range"),
            description=LocalizedText(
                zh="读取一个设备的一个信号键在指定时间段内的原始值，按时间排序。",
                en="Reads raw values of one device key within a time range, ordered by time.",
            ),
            data_source_id=SOURCE_ID,
            parameters=[
                _p("device_id", QueryParamType.IDENTIFIER, "设备", "Device"),
                _p("key_name", QueryParamType.IDENTIFIER, "信号键", "Signal key"),
                _p("start", QueryParamType.TIMESTAMP, "开始时间", "Start"),
                _p("end", QueryParamType.TIMESTAMP, "结束时间", "End"),
            ],
            max_rows=200_000,
            max_range_hours=168,
            version=2,
        ),
        "SELECT deviceid, keyname, ts, value_double\n"
        "FROM raw_telemetry\n"
        "WHERE deviceid = :device_id AND keyname = :key_name\n"
        "  AND ts >= :start AND ts < :end\n"
        "ORDER BY ts\n"
        "LIMIT 200000",
    ),
    (
        QueryTemplate(
            template_id="telemetry-incremental",
            name=LocalizedText(zh="增量读取（水位线）", en="Incremental read (watermark)"),
            description=LocalizedText(
                zh="从上次读取的时间点之后继续读取，用于定时同步。",
                en="Continues after the last timestamp read; used for scheduled sync.",
            ),
            data_source_id=SOURCE_ID,
            parameters=[
                _p("device_id", QueryParamType.IDENTIFIER, "设备", "Device"),
                _p("key_name", QueryParamType.IDENTIFIER, "信号键", "Signal key"),
                _p("watermark", QueryParamType.TIMESTAMP, "水位线", "Watermark"),
            ],
            max_rows=50_000,
            max_range_hours=24,
            version=1,
        ),
        "SELECT deviceid, keyname, ts, value_double\n"
        "FROM raw_telemetry\n"
        "WHERE deviceid = :device_id AND keyname = :key_name\n"
        "  AND ts > :watermark\n"
        "ORDER BY ts\n"
        "LIMIT 50000",
    ),
]

VERSIONS = [
    SignalConfigVersion(
        version=1,
        created_at=datetime.fromisoformat("2026-02-10T08:30:00+00:00"),
        created_by="demo-admin",
        comment="Initial mapping for SIM-S01 (simulated history)",
        content_hash="sha256:" + "1f3a" * 16,
    ),
    SignalConfigVersion(
        version=2,
        created_at=datetime.fromisoformat("2026-02-18T14:05:00+00:00"),
        created_by="demo-admin",
        comment="Added cylinder timing group (simulated history)",
        content_hash="sha256:" + "7c2e" * 16,
    ),
]


def _source() -> DataSourceConfig:
    return DataSourceConfig(
        data_source_id=SOURCE_ID,
        name="SIM IoT telemetry",
        kind=DataSourceKind.SIMULATED,
        engine=None,
        host="sim-iot.local",
        port=5432,
        database="iot_telemetry",
        credential_ref="secret://pdm/sim-iot-readonly",
        read_only=True,
        statement_timeout_s=30,
        max_rows=200_000,
        is_simulated=True,
    )


def _window(scen_dir: Path, start_h: float, hours: float) -> tuple[datetime, datetime]:
    cfg = json.loads((scen_dir / "config.json").read_text(encoding="utf-8"))
    t0 = datetime.fromisoformat(cfg["start"].replace("Z", "+00:00"))
    return t0 + timedelta(hours=start_h), t0 + timedelta(hours=start_h + hours)


def _iso(ts: datetime) -> str:
    return ts.isoformat().replace("+00:00", "Z")


def build_sources(data_dir: Path) -> list[dict[str, object]]:
    datasets = []
    for sid, start_h, hours in DEVICES:
        (scen_dir,) = (data_dir / "scenarios").glob(f"{sid}_*")
        w0, w1 = _window(scen_dir, start_h, hours)
        datasets.append(
            {"dir": f"../scenarios/{scen_dir.name}", "preview_window": {"start": _iso(w0), "end": _iso(w1)}}
        )
    return [{"config": _source().model_dump(mode="json"), "simulated_datasets": datasets}]


def build_studio(data_dir: Path) -> dict[str, object]:
    devices, previews, signals, components, mappings = [], {}, [], [], []
    meta_devices, earliest, latest, total_rows = [], None, None, 0
    sample_rows: list[dict[str, str]] = []
    for sid, start_h, hours in DEVICES:
        (scen_dir,) = (data_dir / "scenarios").glob(f"{sid}_*")
        meta = json.loads((scen_dir / "scenario.json").read_text(encoding="utf-8"))
        topo = json.loads((scen_dir / "topology.json").read_text(encoding="utf-8"))
        w0, w1 = _window(scen_dir, start_h, hours)
        lo, hi = w0.strftime("%Y-%m-%dT%H:%M:%S"), w1.strftime("%Y-%m-%dT%H:%M:%S")
        rows = list(csv.DictReader(io.StringIO(read_text(scen_dir / "raw_telemetry.csv"))))
        device_id = rows[0]["deviceid"]
        counts: dict[str, int] = {}
        series: dict[str, list[list[float]]] = {}
        for r in rows:
            counts[r["keyname"]] = counts.get(r["keyname"], 0) + 1
            if lo <= r["ts"][:19] < hi:
                ts = datetime.fromisoformat(r["ts"].replace("Z", "+00:00"))
                offset = round((ts - w0).total_seconds(), 3)
                series.setdefault(r["keyname"], []).append([offset, float(r["value_double"])])
        if not sample_rows:
            sample_rows = rows[:5]
        total_rows += len(rows)
        ts_all = sorted(r["ts"] for r in rows)
        earliest = min(earliest or ts_all[0], ts_all[0])
        latest = max(latest or ts_all[-1], ts_all[-1])
        keys = sorted(counts)
        meta_devices.append(DeviceKeys(device_id=device_id, key_names=keys))
        devices.append(
            {
                "device_id": device_id,
                "scenario_id": sid,
                "scenario_title": meta["title"],
                "keys": [{"key_name": k, "rows": counts[k]} for k in keys],
            }
        )
        previews[device_id] = {
            "window_start": _iso(w0),
            "window_end": _iso(w1),
            "series": series,
        }
        signals += [{**s, "device_id": device_id} for s in topo["signals"]]
        components += [{**c, "device_id": device_id} for c in topo["components"]]
        mappings += topo["mappings"]
    source = _source()
    metadata = SourceMetadata(
        data_source_id=SOURCE_ID,
        devices=meta_devices,
        earliest_ts=datetime.fromisoformat(earliest.replace("Z", "+00:00")),
        latest_ts=datetime.fromisoformat(latest.replace("Z", "+00:00")),
        is_simulated=True,
    )
    return {
        "is_simulated": True,
        "data_source": source.model_dump(mode="json"),
        "metadata": metadata.model_dump(mode="json"),
        "table": {
            "name": "telemetry",
            "row_count": total_rows,
            "columns": [{"name": n, "type": t, "role": role} for n, t, role in TABLE_COLUMNS],
            "sample_rows": [[r[c] for c, _, _ in TABLE_COLUMNS] for r in sample_rows],
        },
        "devices": devices,
        "templates": [t.model_dump(mode="json") for t, _ in TEMPLATES],
        "template_sql": {t.template_id: sql for t, sql in TEMPLATES},
        "signals": signals,
        "components": components,
        "suggested_mappings": mappings,
        "versions": [v.model_dump(mode="json") for v in VERSIONS],
        "previews": previews,
    }


def write_studio(data_dir: Path) -> Path:
    sources = data_dir / "fixtures" / "studio_sources.json"
    sources.write_bytes((json.dumps(build_sources(data_dir), indent=2) + "\n").encode("utf-8"))
    path = data_dir / "fixtures" / "studio_demo.json"
    text = json.dumps(build_studio(data_dir), ensure_ascii=False, separators=(",", ":"))
    path.write_bytes((text + "\n").encode("utf-8"))
    return path
