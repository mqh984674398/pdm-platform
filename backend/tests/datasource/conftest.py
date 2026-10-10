"""Test databases seeded from simulated raw rows (T009).

SQLite always runs. PostgreSQL runs when PDM_TEST_PG_URL points at a database the tests may write
to (CI service container, or a local throwaway cluster); the adapter itself connects read-only.
"""

from __future__ import annotations

import csv
import io
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Column, DateTime, Float, Integer, MetaData, String, Table, create_engine, text

from app.datasource.schemas import DataSourceConfig, DataSourceKind, SqlTableLayout
from app.datasource.simulated import SimulatedAdapter
from app.datasource.sql import SqlAdapter
from app.simulation.golden import scenario_dir
from app.simulation.writer import read_text

PG_URL = os.environ.get("PDM_TEST_PG_URL")
DATASETS = ["S13", "S14"]  # duplicates + missing rows; jitter + out-of-order rows

# Two layouts with different names prove nothing is tied to one schema (L1-08).
IOTSHARP_LIKE = SqlTableLayout(
    table="telemetrydata",
    device_column="deviceid",
    key_column="keyname",
    time_column="datetime",
    value_columns=["value_double", "value_long"],
)
SIMULATOR_LIKE = SqlTableLayout(
    schema_name="iot",
    table="raw_telemetry",
    device_column="device_id",
    key_column="key_name",
    time_column="ts",
    value_columns=["value"],
)


def raw_rows(sid: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(read_text(scenario_dir(sid) / "raw_telemetry.csv"))))


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def source_config(**kw) -> DataSourceConfig:
    base = dict(
        data_source_id="test-sql",
        name="Test SQL source",
        kind=DataSourceKind.SQL,
        read_only=True,
        statement_timeout_s=10,
        max_rows=200_000,
        is_simulated=True,
    )
    return DataSourceConfig(**{**base, **kw})


def seed_iotsharp_like(url: str, sid: str, naive_zone=UTC) -> None:
    """Naive timestamps (like a ``timestamp without time zone`` column) in ``naive_zone``."""
    engine = create_engine(url)
    md = MetaData()
    table = Table(
        "telemetrydata",
        md,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("deviceid", String(64), nullable=False),
        Column("keyname", String(64), nullable=False),
        Column("datetime", DateTime(timezone=False), nullable=False),
        Column("value_double", Float),
        Column("value_long", Integer),
    )
    md.drop_all(engine)
    md.create_all(engine)
    rows = [
        {
            "deviceid": r["deviceid"],
            "keyname": r["keyname"],
            "datetime": parse_ts(r["ts"]).astimezone(naive_zone).replace(tzinfo=None),
            "value_double": float(r["value_double"]) if r["value_double"] else None,
            "value_long": None,
        }
        for r in raw_rows(sid)
    ]
    with engine.begin() as conn:
        conn.execute(table.insert(), rows)
    engine.dispose()


def seed_simulator_like_pg(url: str, sid: str) -> None:
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS iot CASCADE"))
        conn.execute(text("CREATE SCHEMA iot"))
    md = MetaData(schema="iot")
    table = Table(
        "raw_telemetry",
        md,
        Column("device_id", String(64), nullable=False),
        Column("key_name", String(64), nullable=False),
        Column("ts", DateTime(timezone=True), nullable=False),
        Column("value", Float),
    )
    md.create_all(engine)
    rows = [
        {
            "device_id": r["deviceid"],
            "key_name": r["keyname"],
            "ts": parse_ts(r["ts"]),
            "value": float(r["value_double"]) if r["value_double"] else None,
        }
        for r in raw_rows(sid)
    ]
    with engine.begin() as conn:
        conn.execute(table.insert(), rows)
    engine.dispose()


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path}"


KINDS = ["simulated", "sqlite"] + (["postgresql"] if PG_URL else [])


@pytest.fixture(
    scope="module", params=[(d, k) for d in DATASETS for k in KINDS], ids=lambda p: f"{p[0]}-{p[1]}"
)
def adapter(request, tmp_path_factory):
    sid, kind = request.param
    if kind == "simulated":
        yield sid, SimulatedAdapter(scenario_dir(sid), data_source_id="test-sql")
        return
    if kind == "sqlite":
        url = sqlite_url(tmp_path_factory.mktemp(sid) / "iot.db")
        seed_iotsharp_like(url, sid)
        a = SqlAdapter(source_config(), IOTSHARP_LIKE, url)
    else:
        seed_simulator_like_pg(PG_URL, sid)
        a = SqlAdapter(source_config(), SIMULATOR_LIKE, PG_URL)
    yield sid, a
    a.engine.dispose()


@pytest.fixture(scope="module")
def reference():
    cache: dict[str, SimulatedAdapter] = {}

    def get(sid: str) -> SimulatedAdapter:
        if sid not in cache:
            cache[sid] = SimulatedAdapter(scenario_dir(sid), data_source_id="test-sql")
        return cache[sid]

    return get
