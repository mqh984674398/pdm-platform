"""SQL-specific guarantees: read-only enforcement, bounds, configurable layout (T009)."""

from __future__ import annotations

import threading
from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, OperationalError

from app.core.schemas import TimeWindow
from app.datasource.schemas import SqlTableLayout
from app.datasource.sql import (
    AdapterError,
    BusyError,
    LayoutError,
    QueryLimitError,
    SqlAdapter,
    UnsupportedEngineError,
)

from .conftest import IOTSHARP_LIKE, PG_URL, parse_ts, raw_rows, seed_iotsharp_like, source_config


@pytest.fixture(scope="module")
def db_url(tmp_path_factory):
    url = f"sqlite:///{tmp_path_factory.mktemp('sql') / 'iot.db'}"
    seed_iotsharp_like(url, "S13")
    return url


@pytest.fixture
def adapter(db_url):
    a = SqlAdapter(source_config(), IOTSHARP_LIKE, db_url)
    yield a
    a.engine.dispose()


T0 = parse_ts(raw_rows("S13")[0]["ts"])


def test_writes_are_refused_by_the_database(adapter):
    with adapter.engine.connect() as conn, pytest.raises(OperationalError, match="readonly|read-only"):
        conn.execute(text("DELETE FROM telemetrydata"))


@pytest.mark.skipif(not PG_URL, reason="PDM_TEST_PG_URL not set")
def test_postgres_session_is_read_only_with_timeout():
    from .conftest import SIMULATOR_LIKE, seed_simulator_like_pg

    seed_simulator_like_pg(PG_URL, "S13")
    a = SqlAdapter(source_config(statement_timeout_s=1), SIMULATOR_LIKE, PG_URL)
    try:
        with a.engine.connect() as conn:
            assert conn.execute(text("SHOW default_transaction_read_only")).scalar() == "on"
            assert conn.execute(text("SHOW statement_timeout")).scalar() == "1s"
            with pytest.raises(DBAPIError, match="read-only"):
                conn.execute(text("DELETE FROM iot.raw_telemetry"))
        with a.engine.connect() as conn, pytest.raises(DBAPIError, match="statement timeout"):
            conn.execute(text("SELECT pg_sleep(3)"))
        assert a.inspect_schema().engine == "postgresql"
    finally:
        a.engine.dispose()


def test_non_read_only_configuration_is_rejected(db_url):
    with pytest.raises(AdapterError, match="read-only"):
        SqlAdapter(source_config(read_only=False), IOTSHARP_LIKE, db_url)


def test_unverified_engines_are_refused():
    with pytest.raises(UnsupportedEngineError):
        SqlAdapter(source_config(), IOTSHARP_LIKE, "mysql+pymysql://u:p@localhost/iot")


@pytest.mark.parametrize(
    "change, message",
    [({"table": "telemetry"}, "not found"), ({"time_column": "ts"}, "ts"), ({"value_columns": ["v"]}, "v")],
)
def test_layout_is_checked_against_the_live_schema(db_url, change, message):
    layout = IOTSHARP_LIKE.model_copy(update=change)
    with pytest.raises(LayoutError, match=message):
        SqlAdapter(source_config(), layout, db_url)


def test_row_and_range_bounds(adapter):
    window = TimeWindow(start=T0, end=T0 + timedelta(days=8))
    with pytest.raises(QueryLimitError, match="time range"):
        adapter.query_range("SIM-S13", "M01_BS1_SPD", window, 10)
    ok = TimeWindow(start=T0, end=T0 + timedelta(days=1))
    for bad in (0, 200_001):
        with pytest.raises(QueryLimitError):
            adapter.query_range("SIM-S13", "M01_BS1_SPD", ok, bad)
        with pytest.raises(QueryLimitError):
            adapter.query_incremental("SIM-S13", "M01_BS1_SPD", T0, bad)


def test_concurrency_limit(db_url):
    a = SqlAdapter(source_config(), IOTSHARP_LIKE, db_url, max_concurrency=1, acquire_timeout_s=0.05)
    window = TimeWindow(start=T0, end=T0 + timedelta(days=1))
    held, release = threading.Event(), threading.Event()

    def hold():
        with a.connection():
            held.set()
            release.wait(5)

    t = threading.Thread(target=hold)
    t.start()
    held.wait(5)
    try:
        with pytest.raises(BusyError):
            a.query_range("SIM-S13", "M01_BS1_SPD", window, 10)
    finally:
        release.set()
        t.join()
    assert a.query_range("SIM-S13", "M01_BS1_SPD", window, 10)
    a.engine.dispose()


def test_value_falls_back_to_the_next_value_column(tmp_path):
    url = f"sqlite:///{tmp_path / 'long.db'}"
    seed_iotsharp_like(url, "S13")
    rw = create_engine(url)
    with rw.begin() as conn:
        conn.execute(text("UPDATE telemetrydata SET value_long = 7, value_double = NULL WHERE id = 1"))
    rw.dispose()
    a = SqlAdapter(source_config(), IOTSHARP_LIKE, url)
    first = raw_rows("S13")[0]
    rows = a.query_incremental(first["deviceid"], first["keyname"], T0 - timedelta(seconds=1), 1)
    assert rows[0].value == 7.0
    a.engine.dispose()


def test_naive_timestamps_use_the_configured_zone(tmp_path):
    zone = ZoneInfo("Asia/Shanghai")
    url = f"sqlite:///{tmp_path / 'local.db'}"
    seed_iotsharp_like(url, "S13", naive_zone=zone)
    layout = IOTSHARP_LIKE.model_copy(update={"naive_time_zone": "Asia/Shanghai"})
    a = SqlAdapter(source_config(), layout, url)
    meta = a.discover()
    assert meta.earliest_ts == T0  # stored as local time, returned as UTC
    window = TimeWindow(start=T0, end=T0 + timedelta(hours=1))
    assert a.query_range("SIM-S13", "M01_BS1_SPD", window, 10)[0].ts == T0
    a.engine.dispose()


def test_layout_defaults_mark_assumptions_unverified():
    layout = SqlTableLayout(
        table="t", device_column="d", key_column="k", time_column="ts", value_columns=["v"]
    )
    assert layout.verified is False and layout.naive_time_zone == "UTC"
