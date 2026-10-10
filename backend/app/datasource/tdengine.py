"""Read-only TDengine (涛思数据) time-series adapter over the taosAdapter REST API (D-035).

TDengine is the production IoT telemetry store. The platform talks to it through taosAdapter's REST
endpoint (``POST http(s)://host:6041/rest/sql/<database>``) with HTTP basic authentication, so no
native client library has to be installed on the Windows server.

Where telemetry lives is configuration (:class:`TdengineLayout`) and is checked against ``DESCRIBE``
on start-up. Two layouts are supported:

* wide (the usual TDengine model): one super table, one row per timestamp, one numeric column per
  signal key, the device identified by a tag column;
* narrow: one super table with a key column and one or more value columns.

Read-only is enforced three ways: the configured account must be a TDengine user with read
privileges only; this adapter only ever sends SELECT, SHOW and DESCRIBE statements it builds itself
from validated identifiers and escaped literals; and administrator templates pass ``sql_guard``.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from pydantic import Field

from app.core.schemas import ContractModel, TimeWindow
from app.datasource.adapter import TimeSeriesAdapter
from app.datasource.schemas import (
    ColumnInfo,
    DataSourceConfig,
    DeviceKeys,
    RawTelemetryRow,
    SourceMetadata,
    SourceSchema,
    TableInfo,
)
from app.datasource.sql import AdapterError, BusyError, LayoutError, QueryLimitError

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,191}$")
NUMERIC_TYPES = {
    "TINYINT", "SMALLINT", "INT", "BIGINT", "FLOAT", "DOUBLE", "BOOL",
    "TINYINT UNSIGNED", "SMALLINT UNSIGNED", "INT UNSIGNED", "BIGINT UNSIGNED",
}  # fmt: skip
READ_STATEMENTS = ("select", "show", "describe")
MAX_STABLES = 200
MAX_STRING = 256


class TdengineLayout(ContractModel):
    """Where telemetry lives in a TDengine database. Configured per source, never assumed (L1-08)."""

    stable: str = Field(description="Super table holding the telemetry")
    device_tag: str = Field(description="Tag (or column) identifying the device")
    time_column: str = "ts"
    key_column: str | None = Field(
        default=None, description="Narrow layout only: column holding the signal key name"
    )
    value_columns: list[str] = Field(
        default_factory=list,
        description="Narrow layout: value columns, first non-null wins. Wide layout: the signal "
        "columns to expose (empty = every numeric column).",
    )
    naive_time_zone: str = Field(
        default="UTC", description="Zone for timestamps the server returns without an offset"
    )
    verified: bool = Field(
        default=False, description="True only after the layout was checked against the real database"
    )


def ident(name: str) -> str:
    if not IDENT.match(name):
        raise AdapterError(f"invalid identifier '{name}'")
    return f"`{name}`"


def literal(value: object) -> str:
    """Render a bound parameter as a TDengine literal. Strings are length-checked and escaped."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise AdapterError("timestamps need a time zone")
        return "'" + value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z'"
    s = str(value)
    if len(s) > MAX_STRING or any(c in s for c in "\x00\n\r"):
        raise AdapterError("string parameter is too long or contains control characters")
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


PLACEHOLDER = re.compile(r"(?<![:\w]):([a-z_][a-z0-9_]*)\b")


def render(sql: str, params: Mapping[str, object]) -> str:
    """Substitute ``:name`` placeholders outside string literals with escaped literals."""
    out, i = [], 0
    while i < len(sql):
        if sql[i] == "'":
            j = i + 1
            while j < len(sql) and not (sql[j] == "'" and sql[j - 1] != "\\"):
                j += 1
            out.append(sql[i : j + 1])
            i = j + 1
            continue
        m = PLACEHOLDER.match(sql, i) if sql[i] == ":" and (i == 0 or sql[i - 1] != ":") else None
        if m:
            if m.group(1) not in params:
                raise AdapterError(f"missing parameter: {m.group(1)}")
            out.append(literal(params[m.group(1)]))
            i = m.end()
            continue
        out.append(sql[i])
        i += 1
    return "".join(out)


class TdengineAdapter(TimeSeriesAdapter):
    engine_name = "tdengine"

    def __init__(
        self,
        config: DataSourceConfig,
        layout: TdengineLayout,
        credential: str,
        *,
        scheme: str = "http",
        max_range_hours: float = 168,
        max_concurrency: int = 4,
        acquire_timeout_s: float = 5,
        transport: httpx.BaseTransport | None = None,
    ):
        if not config.read_only:
            raise AdapterError("data sources must be configured read-only")
        if not (config.host and config.database):
            raise AdapterError(f"{config.data_source_id}: TDengine sources need host and database")
        user, sep, password = credential.partition(":")
        if not sep or not user:
            raise AdapterError("TDengine credential must look like <user>:<password>")
        self.data_source_id = config.data_source_id
        self.is_simulated = config.is_simulated
        self.config = config
        self.layout = layout
        self.max_range = timedelta(hours=max_range_hours)
        self._slots = threading.BoundedSemaphore(max_concurrency)
        self._acquire_timeout = acquire_timeout_s
        self._zone = ZoneInfo(layout.naive_time_zone)
        self._url = f"{scheme}://{config.host}:{config.port or 6041}/rest/sql/{config.database}"
        self._client = httpx.Client(
            auth=(user, password), timeout=config.statement_timeout_s + 5, transport=transport
        )
        self._source_ref = f"{self.data_source_id}:{layout.stable}"
        self._keys: list[str] | None = None

    # --- transport -----------------------------------------------------------------------------

    def sql(self, statement: str) -> tuple[list[str], list[str], list[list[Any]]]:
        """Run one read statement; returns (column names, column types, rows)."""
        if not statement.lstrip().lower().startswith(READ_STATEMENTS):
            raise AdapterError("only SELECT, SHOW and DESCRIBE statements are sent to TDengine")
        if not self._slots.acquire(timeout=self._acquire_timeout):
            raise BusyError("too many concurrent queries for this data source")
        try:
            resp = self._client.post(self._url, content=statement.encode("utf-8"))
        except httpx.HTTPError as exc:
            raise AdapterError(f"TDengine is not reachable: {exc.__class__.__name__}") from exc
        finally:
            self._slots.release()
        try:
            body = resp.json()
        except ValueError as exc:
            raise AdapterError(f"TDengine returned HTTP {resp.status_code}") from exc
        if resp.status_code != 200 or body.get("code", 0) != 0:
            raise AdapterError(f"TDengine error: {body.get('desc') or resp.status_code}")
        meta = body.get("column_meta") or []
        return [m[0] for m in meta], [str(m[1]).upper() for m in meta], body.get("data") or []

    # --- layout --------------------------------------------------------------------------------

    def describe(self, table: str) -> list[tuple[str, str, bool]]:
        """(name, type, is_tag) for each column of ``table``."""
        names, _, rows = self.sql(f"DESCRIBE {ident(table)}")
        col = {n.lower(): i for i, n in enumerate(names)}
        out = []
        for r in rows:
            note = str(r[col["note"]]).upper() if "note" in col else ""
            out.append((str(r[col["field"]]), str(r[col["type"]]).upper(), note == "TAG"))
        return out

    def check_layout(self) -> None:
        lay = self.layout
        cols = {n: (t, tag) for n, t, tag in self.describe(lay.stable)}
        needed = [lay.device_tag, lay.time_column, *lay.value_columns]
        if lay.key_column:
            needed.append(lay.key_column)
        missing = [c for c in needed if c not in cols]
        if missing:
            raise LayoutError(f"columns not found in '{lay.stable}': {', '.join(missing)}")
        if not lay.key_column:
            keys = lay.value_columns or [n for n, (t, tag) in cols.items() if not tag and t in NUMERIC_TYPES]
            if not keys:
                raise LayoutError(f"'{lay.stable}' has no numeric columns to read")
            self._keys = keys
        elif not lay.value_columns:
            raise LayoutError("narrow TDengine layouts need value_columns")

    def keys(self) -> list[str]:
        if self._keys is None and not self.layout.key_column:
            self.check_layout()
        return list(self._keys or [])

    # --- time handling -------------------------------------------------------------------------

    def to_db_time(self, ts: datetime) -> datetime:
        return ts

    def from_db_time(self, value: Any) -> datetime:
        if isinstance(value, int | float):
            return datetime.fromtimestamp(value / 1000, UTC)
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=self._zone)
        return ts.astimezone(UTC)

    def _check_limit(self, limit: int) -> None:
        if limit < 1 or limit > self.config.max_rows:
            raise QueryLimitError(f"limit must be between 1 and {self.config.max_rows}")

    # --- interface -----------------------------------------------------------------------------

    def discover(self) -> SourceMetadata:
        lay = self.layout
        st, dev, t = ident(lay.stable), ident(lay.device_tag), ident(lay.time_column)
        devices: dict[str, list[str]] = {}
        if lay.key_column:
            _, _, rows = self.sql(f"SELECT DISTINCT {dev}, {ident(lay.key_column)} FROM {st}")
            for d, k in rows:
                devices.setdefault(str(d), []).append(str(k))
            devices = {d: sorted(k) for d, k in sorted(devices.items())}
        else:
            keys = self.keys()
            _, _, rows = self.sql(f"SELECT DISTINCT {dev} FROM {st}")
            devices = {str(r[0]): list(keys) for r in sorted(rows, key=lambda r: str(r[0]))}
        _, _, span = self.sql(f"SELECT FIRST({t}), LAST({t}) FROM {st}")
        lo, hi = (span[0] if span else (None, None))[:2]
        return SourceMetadata(
            data_source_id=self.data_source_id,
            devices=[DeviceKeys(device_id=d, key_names=k) for d, k in devices.items()],
            earliest_ts=self.from_db_time(lo) if lo is not None else None,
            latest_ts=self.from_db_time(hi) if hi is not None else None,
            is_simulated=self.is_simulated,
        )

    def inspect_schema(self) -> SourceSchema:
        _, _, rows = self.sql("SHOW STABLES")
        tables = [
            TableInfo(
                schema_name=None,
                name=str(r[0]),
                columns=[
                    ColumnInfo(name=n, type=typ, nullable=not tag) for n, typ, tag in self.describe(str(r[0]))
                ],
            )
            for r in rows[:MAX_STABLES]
            if IDENT.match(str(r[0]))
        ]
        _, _, version = self.sql("SELECT SERVER_VERSION()")
        return SourceSchema(
            data_source_id=self.data_source_id,
            engine=self.engine_name,
            server_version=str(version[0][0]) if version else None,
            tables=tables,
            is_simulated=self.is_simulated,
        )

    def query_range(
        self, device_id: str, key_name: str, window: TimeWindow, limit: int
    ) -> list[RawTelemetryRow]:
        self._check_limit(limit)
        if window.end - window.start > self.max_range:
            raise QueryLimitError(f"time range exceeds {self.max_range.total_seconds() / 3600:g} h")
        t = ident(self.layout.time_column)
        where = f"{t} >= {literal(window.start)} AND {t} < {literal(window.end)}"
        return self._series(device_id, key_name, where, limit)

    def query_incremental(
        self, device_id: str, key_name: str, since: datetime, limit: int
    ) -> list[RawTelemetryRow]:
        self._check_limit(limit)
        return self._series(
            device_id, key_name, f"{ident(self.layout.time_column)} > {literal(since)}", limit
        )

    def _series(self, device_id: str, key_name: str, where: str, limit: int) -> list[RawTelemetryRow]:
        lay = self.layout
        t = ident(lay.time_column)
        cond = f"{ident(lay.device_tag)} = {literal(device_id)} AND {where}"
        if lay.key_column:
            vals = [ident(c) for c in lay.value_columns]
            value = vals[0] if len(vals) == 1 else ", ".join(vals)
            cond += f" AND {ident(lay.key_column)} = {literal(key_name)}"
        else:
            if key_name not in self.keys():
                raise AdapterError(f"unknown signal key '{key_name}'")
            value = ident(key_name)
        _, _, rows = self.sql(
            f"SELECT {t}, {value} FROM {ident(lay.stable)} WHERE {cond} ORDER BY {t} LIMIT {int(limit)}"
        )
        out = []
        for r in rows:
            v = next((x for x in r[1:] if x is not None), None)
            out.append(
                RawTelemetryRow(
                    device_id=device_id,
                    key_name=key_name,
                    ts=self.from_db_time(r[0]),
                    value=None if v is None else float(v),
                    source_ref=self._source_ref,
                    is_simulated=self.is_simulated,
                    arrival_seq=None,
                )
            )
        return out

    def run_template(
        self, sql: str, params: Mapping[str, object], limit: int
    ) -> tuple[list[str], list[list[Any]]]:
        """Run an approved template; fetches at most ``limit + 1`` rows to detect truncation."""
        rendered = render(sql, params).rstrip().rstrip(";")
        if not re.search(r"\blimit\s+\d+\s*$", rendered, re.IGNORECASE):
            rendered += f" LIMIT {int(limit) + 1}"
        names, _, rows = self.sql(rendered)
        return names, rows[: limit + 1]
