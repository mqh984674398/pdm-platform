"""Built-in read-only query templates registered at start-up (L1-05, D-032).

A fresh installation has an empty template registry, so the Data Source Studio had nothing to choose at
its template step. ``ensure_standard_templates`` registers two bounded SELECT templates for every loaded
source that has never had a template: one for a key over a time range and one incremental read. Their
SQL is generated from the source's configured table layout and passes the same ``sql_guard`` checks as
an administrator's template. Sources with any template history (including retired ones) are left alone,
so an administrator's retirement or replacement is never undone.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.schemas import LocalizedText
from app.core.security import Principal, Role
from app.datasource.adapter import TimeSeriesAdapter
from app.datasource.query_service.registry import QueryTemplateRecord, TemplateRegistry
from app.datasource.query_service.service import allowed_tables
from app.datasource.query_service.sources import DataSourceRegistry
from app.datasource.schemas import QueryParameter, QueryParamType, QueryTemplateSpec
from app.datasource.sql import AdapterError, SqlAdapter
from app.datasource.tdengine import TdengineAdapter

SYSTEM = Principal(user_id="system:install", role=Role.ADMIN)
# The Studio demo source keeps the template ids its fixtures and tests use.
UNPREFIXED_SOURCES = {"sim-iot"}
RANGE_ROWS, RANGE_HOURS = 200_000, 168
INCREMENTAL_ROWS, INCREMENTAL_HOURS = 50_000, 24


def _p(name: str, kind: QueryParamType, zh: str, en: str) -> QueryParameter:
    return QueryParameter(name=name, type=kind, label=LocalizedText(zh=zh, en=en))


def _columns(adapter: TimeSeriesAdapter) -> tuple[str, str, str, str, str]:
    """(table, device, key, time, value) as named in the source."""
    if isinstance(adapter, SqlAdapter):
        lay = adapter.layout
        table = f"{lay.schema_name}.{lay.table}" if lay.schema_name else lay.table
        return table, lay.device_column, lay.key_column, lay.time_column, lay.value_columns[0]
    return "raw_telemetry", "deviceid", "keyname", "ts", "value_double"


def template_id(data_source_id: str, base: str) -> str:
    if data_source_id in UNPREFIXED_SOURCES:
        return base
    slug = re.sub(r"[^a-z0-9-]+", "-", data_source_id.lower()).strip("-") or "source"
    return f"{slug[: 62 - len(base)]}-{base}".strip("-")


def _tdengine_templates(data_source_id: str, adapter: TdengineAdapter) -> list[QueryTemplateSpec]:
    """Wide TDengine layouts have one column per key, so the templates read every exposed column."""
    lay = adapter.layout
    if lay.key_column:
        cols = ", ".join([lay.key_column, *lay.value_columns])
        key_cond, ident = (
            f" AND {lay.key_column} = :key_name",
            [
                _p("device_id", QueryParamType.IDENTIFIER, "设备", "Device"),
                _p("key_name", QueryParamType.IDENTIFIER, "信号键", "Signal key"),
            ],
        )
    else:
        cols = ", ".join(adapter.layout.value_columns or ["*"]) if adapter.layout.value_columns else "*"
        key_cond, ident = "", [_p("device_id", QueryParamType.IDENTIFIER, "设备", "Device")]
    sel = f"{lay.time_column}, {cols}" if cols != "*" else "*"
    head = f"SELECT {sel}\nFROM {lay.stable}\nWHERE {lay.device_tag} = :device_id{key_cond}\n"
    t = lay.time_column
    return [
        QueryTemplateSpec(
            template_id=template_id(data_source_id, "telemetry-by-key-range"),
            name=LocalizedText(zh="按设备查询时间段", en="Device telemetry over a time range"),
            description=LocalizedText(
                zh="读取一个设备在指定时间段内的原始遥测值，按时间排序。",
                en="Reads raw telemetry of one device within a time range, ordered by time.",
            ),
            data_source_id=data_source_id,
            parameters=[
                *ident,
                _p("start", QueryParamType.TIMESTAMP, "开始时间", "Start"),
                _p("end", QueryParamType.TIMESTAMP, "结束时间", "End"),
            ],
            sql=f"{head}  AND {t} >= :start AND {t} < :end\nORDER BY {t}\nLIMIT {RANGE_ROWS}",
            max_rows=RANGE_ROWS,
            max_range_hours=RANGE_HOURS,
        ),
        QueryTemplateSpec(
            template_id=template_id(data_source_id, "telemetry-incremental"),
            name=LocalizedText(zh="增量读取（水位线）", en="Incremental read (watermark)"),
            description=LocalizedText(
                zh="从上次读取的时间点之后继续读取，用于定时同步。",
                en="Continues after the last timestamp read; used for scheduled sync.",
            ),
            data_source_id=data_source_id,
            parameters=[*ident, _p("watermark", QueryParamType.TIMESTAMP, "水位线", "Watermark")],
            sql=f"{head}  AND {t} > :watermark\nORDER BY {t}\nLIMIT {INCREMENTAL_ROWS}",
            max_rows=INCREMENTAL_ROWS,
            max_range_hours=INCREMENTAL_HOURS,
        ),
    ]


def standard_templates(data_source_id: str, adapter: TimeSeriesAdapter) -> list[QueryTemplateSpec]:
    if isinstance(adapter, TdengineAdapter):
        return _tdengine_templates(data_source_id, adapter)
    table, device, key, time, value = _columns(adapter)
    head = (
        f"SELECT {device}, {key}, {time}, {value}\nFROM {table}\n"
        f"WHERE {device} = :device_id AND {key} = :key_name\n"
    )
    ident = [
        _p("device_id", QueryParamType.IDENTIFIER, "设备", "Device"),
        _p("key_name", QueryParamType.IDENTIFIER, "信号键", "Signal key"),
    ]
    return [
        QueryTemplateSpec(
            template_id=template_id(data_source_id, "telemetry-by-key-range"),
            name=LocalizedText(zh="按信号键查询时间段", en="Signal key over a time range"),
            description=LocalizedText(
                zh="读取一个设备的一个信号键在指定时间段内的原始值，按时间排序。",
                en="Reads raw values of one device key within a time range, ordered by time.",
            ),
            data_source_id=data_source_id,
            parameters=[
                *ident,
                _p("start", QueryParamType.TIMESTAMP, "开始时间", "Start"),
                _p("end", QueryParamType.TIMESTAMP, "结束时间", "End"),
            ],
            sql=f"{head}  AND {time} >= :start AND {time} < :end\nORDER BY {time}\nLIMIT {RANGE_ROWS}",
            max_rows=RANGE_ROWS,
            max_range_hours=RANGE_HOURS,
        ),
        QueryTemplateSpec(
            template_id=template_id(data_source_id, "telemetry-incremental"),
            name=LocalizedText(zh="增量读取（水位线）", en="Incremental read (watermark)"),
            description=LocalizedText(
                zh="从上次读取的时间点之后继续读取，用于定时同步。",
                en="Continues after the last timestamp read; used for scheduled sync.",
            ),
            data_source_id=data_source_id,
            parameters=[*ident, _p("watermark", QueryParamType.TIMESTAMP, "水位线", "Watermark")],
            sql=f"{head}  AND {time} > :watermark\nORDER BY {time}\nLIMIT {INCREMENTAL_ROWS}",
            max_rows=INCREMENTAL_ROWS,
            max_range_hours=INCREMENTAL_HOURS,
        ),
    ]


def ensure_standard_templates(session: Session, sources: DataSourceRegistry) -> list[str]:
    """Register the standard templates for sources that never had one; returns the ids created."""
    registry = TemplateRegistry(session)
    have = set(session.scalars(select(QueryTemplateRecord.data_source_id).distinct()))
    created: list[str] = []
    for config in sources.configs():
        if config.data_source_id in have:
            continue
        adapter = sources.adapter(config.data_source_id)
        try:
            tables = allowed_tables(adapter)
        except AdapterError as exc:  # e.g. TDengine not reachable at start-up: retried next start
            print(f"Skipped built-in templates for {config.data_source_id}: {exc}")
            continue
        for spec in standard_templates(config.data_source_id, adapter):
            if registry.history(spec.template_id):
                continue
            registry.create(spec, SYSTEM, tables)
            created.append(spec.template_id)
    session.commit()
    return created
