"""Read-only SQL time-series adapter (L1-01..L1-06, L1-08).

Where telemetry lives is configuration (:class:`SqlTableLayout`), checked against the live schema on
start-up, so nothing depends on the example query's names. Every query is built with SQLAlchemy Core
from validated identifiers and bound parameters; no SQL text is ever accepted from callers.

Read-only is enforced on the server side in addition to read-only credentials (L1-02):
PostgreSQL sessions start with ``default_transaction_read_only=on`` and a ``statement_timeout``;
SQLite connections run with ``PRAGMA query_only``. Other engines are refused until verified.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Float, MetaData, Table, cast, create_engine, event, func, inspect, literal, select
from sqlalchemy.engine import URL, Connection, Engine, make_url
from sqlalchemy.exc import NoSuchTableError

from app.core.schemas import TimeWindow
from app.datasource.adapter import TimeSeriesAdapter
from app.datasource.schemas import (
    ColumnInfo,
    DataSourceConfig,
    DeviceKeys,
    RawTelemetryRow,
    SourceMetadata,
    SourceSchema,
    SqlTableLayout,
    TableInfo,
)

SUPPORTED_ENGINES = ("postgresql", "sqlite")
SYSTEM_SCHEMAS = {"information_schema", "pg_catalog", "pg_toast"}


class AdapterError(Exception):
    """Base class for data source errors that are safe to show to users."""


class LayoutError(AdapterError):
    """The configured table layout does not match the live schema."""


class QueryLimitError(AdapterError):
    """A request exceeds the configured row or time-range bounds (L1-06)."""


class BusyError(AdapterError):
    """Too many concurrent queries against this source (L1-06)."""


class UnsupportedEngineError(AdapterError):
    """The engine has not been verified for read-only enforcement."""


class SqlAdapter(TimeSeriesAdapter):
    def __init__(
        self,
        config: DataSourceConfig,
        layout: SqlTableLayout,
        url: str | URL,
        *,
        max_range_hours: float = 168,
        max_concurrency: int = 4,
        acquire_timeout_s: float = 5,
    ):
        if not config.read_only:
            raise AdapterError("data sources must be configured read-only")
        self.data_source_id = config.data_source_id
        self.is_simulated = config.is_simulated
        self.config = config
        self.layout = layout
        self.max_range = timedelta(hours=max_range_hours)
        self._slots = threading.BoundedSemaphore(max_concurrency)
        self._acquire_timeout = acquire_timeout_s
        self.engine = self._create_engine(url)
        self._table = self._reflect()
        cols = self._table.c
        self._device = cols[layout.device_column]
        self._key = cols[layout.key_column]
        self._time = cols[layout.time_column]
        values = [cast(cols[c], Float) for c in layout.value_columns]
        self._value = values[0] if len(values) == 1 else func.coalesce(*values)
        self._arrival = cols[layout.arrival_column] if layout.arrival_column else None
        self._naive = not getattr(self._time.type, "timezone", False)
        self._zone = ZoneInfo(layout.naive_time_zone)
        where = f"{layout.schema_name}." if layout.schema_name else ""
        self._source_ref = f"{self.data_source_id}:{where}{layout.table}"

    # --- setup ---------------------------------------------------------------------------------

    def _create_engine(self, url: str | URL) -> Engine:
        dialect = make_url(url).get_backend_name()
        if dialect not in SUPPORTED_ENGINES:
            raise UnsupportedEngineError(
                f"engine '{dialect}' is not verified for read-only access; supported: {SUPPORTED_ENGINES}"
            )
        timeout_ms = int(self.config.statement_timeout_s * 1000)
        if dialect == "postgresql":
            options = f"-c default_transaction_read_only=on -c statement_timeout={timeout_ms}"
            engine = create_engine(url, pool_pre_ping=True, connect_args={"options": options})
        else:
            engine = create_engine(url)

            @event.listens_for(engine, "connect")
            def _query_only(dbapi_conn, _record):  # pragma: no branch - sqlite only
                dbapi_conn.execute("PRAGMA query_only = ON")

        return engine

    def _reflect(self) -> Table:
        lay = self.layout
        try:
            table = Table(lay.table, MetaData(), schema=lay.schema_name, autoload_with=self.engine)
        except NoSuchTableError as exc:
            raise LayoutError(f"table '{lay.table}' not found") from exc
        needed = [lay.device_column, lay.key_column, lay.time_column, *lay.value_columns]
        if lay.arrival_column:
            needed.append(lay.arrival_column)
        missing = [c for c in needed if c not in table.c]
        if missing:
            raise LayoutError(f"columns not found in '{lay.table}': {', '.join(missing)}")
        return table

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        if not self._slots.acquire(timeout=self._acquire_timeout):
            raise BusyError("too many concurrent queries for this data source")
        try:
            with self.engine.connect() as conn:
                yield conn
        finally:
            self._slots.release()

    # --- time handling -------------------------------------------------------------------------

    def to_db_time(self, ts: datetime) -> datetime:
        return ts.astimezone(self._zone).replace(tzinfo=None) if self._naive else ts

    def from_db_time(self, ts: datetime) -> datetime:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=self._zone)
        return ts.astimezone(UTC)

    def _check_limit(self, limit: int) -> None:
        if limit < 1 or limit > self.config.max_rows:
            raise QueryLimitError(f"limit must be between 1 and {self.config.max_rows}")

    # --- interface -----------------------------------------------------------------------------

    def discover(self) -> SourceMetadata:
        with self.connection() as conn:
            pairs = conn.execute(
                select(self._device, self._key).distinct().order_by(self._device, self._key)
            ).all()
            lo, hi = conn.execute(select(func.min(self._time), func.max(self._time))).one()
        devices: dict[str, list[str]] = {}
        for device, key in pairs:
            devices.setdefault(str(device), []).append(str(key))
        return SourceMetadata(
            data_source_id=self.data_source_id,
            devices=[DeviceKeys(device_id=d, key_names=k) for d, k in devices.items()],
            earliest_ts=self.from_db_time(lo) if lo else None,
            latest_ts=self.from_db_time(hi) if hi else None,
            is_simulated=self.is_simulated,
        )

    def inspect_schema(self) -> SourceSchema:
        with self.connection() as conn:
            insp = inspect(conn)
            schemas = [s for s in insp.get_schema_names() if s not in SYSTEM_SCHEMAS]
            tables = [
                TableInfo(
                    schema_name=None if self.engine.dialect.name == "sqlite" else schema,
                    name=name,
                    columns=[
                        ColumnInfo(name=c["name"], type=str(c["type"]), nullable=bool(c["nullable"]))
                        for c in insp.get_columns(name, schema=schema)
                    ],
                )
                for schema in schemas
                for name in insp.get_table_names(schema=schema)
            ]
            version = conn.dialect.server_version_info
        return SourceSchema(
            data_source_id=self.data_source_id,
            engine=self.engine.dialect.name,
            server_version=".".join(str(v) for v in version) if version else None,
            tables=tables,
            is_simulated=self.is_simulated,
        )

    def query_range(
        self, device_id: str, key_name: str, window: TimeWindow, limit: int
    ) -> list[RawTelemetryRow]:
        self._check_limit(limit)
        if window.end - window.start > self.max_range:
            raise QueryLimitError(f"time range exceeds {self.max_range.total_seconds() / 3600:g} h")
        stmt = self._series(device_id, key_name).where(
            self._time >= self.to_db_time(window.start), self._time < self.to_db_time(window.end)
        )
        return self._run(stmt.limit(limit), device_id, key_name)

    def query_incremental(
        self, device_id: str, key_name: str, since: datetime, limit: int
    ) -> list[RawTelemetryRow]:
        self._check_limit(limit)
        stmt = self._series(device_id, key_name).where(self._time > self.to_db_time(since))
        return self._run(stmt.limit(limit), device_id, key_name)

    def _series(self, device_id: str, key_name: str):
        arrival = self._arrival if self._arrival is not None else literal(None)
        order = [self._time] if self._arrival is None else [self._time, self._arrival]
        return (
            select(self._time, self._value, arrival)
            .where(self._device == device_id, self._key == key_name)
            .order_by(*order)
        )

    def _run(self, stmt, device_id: str, key_name: str) -> list[RawTelemetryRow]:
        with self.connection() as conn:
            rows = conn.execute(stmt).all()
        return [
            RawTelemetryRow(
                device_id=device_id,
                key_name=key_name,
                ts=self.from_db_time(ts),
                value=None if value is None else float(value),
                source_ref=self._source_ref,
                is_simulated=self.is_simulated,
                arrival_seq=None if seq is None else int(seq),
            )
            for ts, value, seq in rows
        ]
