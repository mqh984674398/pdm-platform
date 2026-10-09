"""Executes approved templates with bound, type-checked parameters under the source's limits."""

from __future__ import annotations

import re
import time
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import text

from app.datasource.query_service.registry import QueryTemplateRecord
from app.datasource.query_service.sources import DataSourceRegistry
from app.datasource.schemas import QueryParameter, QueryParamType, QueryResult, QueryRunRequest
from app.datasource.sql import AdapterError, QueryLimitError, SqlAdapter

MAX_STRING = 256
ALLOWLIST_TTL_S = 300
# SQLite has no timestamp type: raw template results carry timestamps as text.
SQLITE_TS = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(\.\d+)?$")


class ParameterError(AdapterError):
    pass


def allowed_tables(adapter: SqlAdapter) -> set[str]:
    names: set[str] = set()
    for t in adapter.inspect_schema().tables:
        names.add(t.name.lower())
        if t.schema_name:
            names.add(f"{t.schema_name}.{t.name}".lower())
    return names


class QueryService:
    def __init__(self, sources: DataSourceRegistry, clock=time.monotonic):
        self.sources = sources
        self._clock = clock
        self._allow: dict[str, tuple[float, set[str]]] = {}

    def sql_adapter(self, data_source_id: str) -> SqlAdapter:
        adapter = self.sources.adapter(data_source_id)
        if not isinstance(adapter, SqlAdapter):
            raise AdapterError("query templates run only on SQL data sources")
        return adapter

    def identifier_allowlist(self, adapter: SqlAdapter) -> set[str]:
        """Device ids and key names from read-only discovery, cached briefly."""
        cached = self._allow.get(adapter.data_source_id)
        if cached and self._clock() - cached[0] < ALLOWLIST_TTL_S:
            return cached[1]
        meta = adapter.discover()
        names = {d.device_id for d in meta.devices} | {k for d in meta.devices for k in d.key_names}
        self._allow[adapter.data_source_id] = (self._clock(), names)
        return names

    def bind(self, params: list[QueryParameter], given: dict, allowlist: set[str]) -> dict:
        declared = {p.name: p for p in params}
        unknown = set(given) - set(declared)
        if unknown:
            raise ParameterError(f"unknown parameters: {', '.join(sorted(unknown))}")
        out: dict[str, object] = {}
        for name, p in declared.items():
            if name not in given:
                if p.required:
                    raise ParameterError(f"missing parameter: {name}")
                out[name] = None
                continue
            out[name] = self._coerce(p, given[name], allowlist)
        return out

    @staticmethod
    def _coerce(p: QueryParameter, value: object, allowlist: set[str]) -> object:
        try:
            if p.type == QueryParamType.INTEGER:
                if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
                    raise ValueError
                return int(value)  # type: ignore[arg-type]
            if p.type == QueryParamType.FLOAT:
                if isinstance(value, bool):
                    raise ValueError
                return float(value)  # type: ignore[arg-type]
            if p.type == QueryParamType.TIMESTAMP:
                ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    raise ParameterError(f"{p.name}: timestamp needs a time zone")
                return ts
        except (TypeError, ValueError) as exc:
            raise ParameterError(f"{p.name}: expected {p.type.value.lower()}") from exc
        s = str(value)
        if len(s) > MAX_STRING:
            raise ParameterError(f"{p.name}: longer than {MAX_STRING} characters")
        if p.type == QueryParamType.IDENTIFIER and s not in allowlist:
            raise ParameterError(f"{p.name}: not a known device or key")
        return s

    def run(self, template: QueryTemplateRecord, request: QueryRunRequest) -> QueryResult:
        spec = template.to_spec()
        adapter = self.sql_adapter(spec.data_source_id)
        config = self.sources.config(spec.data_source_id)
        params = self.bind(spec.parameters, request.parameters, self.identifier_allowlist(adapter))
        start, end = params.get("start"), params.get("end")
        if isinstance(start, datetime) and isinstance(end, datetime):
            if end <= start:
                raise QueryLimitError("end must be after start")
            hours = (end - start).total_seconds() / 3600
            limit_h = min(spec.max_range_hours, adapter.max_range.total_seconds() / 3600)
            if hours > limit_h:
                raise QueryLimitError(f"time range exceeds {limit_h:g} h")
        params = {k: adapter.to_db_time(v) if isinstance(v, datetime) else v for k, v in params.items()}
        limit = min(spec.max_rows, config.max_rows)
        with adapter.connection() as conn:
            result = conn.execute(text(spec.sql), params)
            columns = list(result.keys())
            rows = result.fetchmany(limit + 1)
            result.close()
        return QueryResult(
            template_id=template.template_id,
            template_version=template.version,
            data_source_id=spec.data_source_id,
            columns=columns,
            rows=[[_json_value(v, adapter) for v in r] for r in rows[:limit]],
            row_count=min(len(rows), limit),
            truncated=len(rows) > limit,
            executed_at=datetime.now(UTC),
            is_simulated=config.is_simulated,
        )


def _json_value(v: object, adapter: SqlAdapter) -> str | int | float | bool | None:
    if isinstance(v, str) and adapter.engine.dialect.name == "sqlite" and SQLITE_TS.match(v):
        v = datetime.fromisoformat(v)
    if v is None or isinstance(v, bool | int | float | str):
        return v  # type: ignore[return-value]
    if isinstance(v, datetime):
        return adapter.from_db_time(v).isoformat().replace("+00:00", "Z")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return str(v)
