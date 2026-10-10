"""Data Source Studio support endpoints (T011, UI-04): connection checks, table layout, devices, and
per-device suggestions. Nothing here accepts or returns SQL text or connection details.

Suggestions come from the saved signal configuration first; for simulated sources the simulator's
topology fills in the rest. Real sources get component suggestions once topology exists (T014).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.schemas import ContractModel, LocalizedText, TimeWindow
from app.core.security import Principal, Role, require
from app.datasource.adapter import TimeSeriesAdapter
from app.datasource.query_service.sources import DataSourceRegistry
from app.datasource.simulated import RAW_COLUMNS, SimulatedAdapter
from app.datasource.sql import AdapterError, SqlAdapter
from app.equipment.schemas import ComponentInstance
from app.signals.registry import SignalConfigStore
from app.signals.schemas import SignalDefinition, SignalMapping

router = APIRouter(tags=["studio"])
DB = Annotated[Session, Depends(get_session)]
Viewer = Annotated[Principal, Depends(require(Role.VIEWER))]
Engineer = Annotated[Principal, Depends(require(Role.ENGINEER))]

ColumnRole = Literal["device", "key", "time", "value"]
SIMULATED_ROLES: dict[str, ColumnRole] = {
    "deviceid": "device",
    "keyname": "key",
    "ts": "time",
    "value_double": "value",
}
MAX_TIMEOUT_S = 300
MAX_ROWS = 2_000_000
DEFAULT_PREVIEW = timedelta(hours=24)


class UnknownDeviceError(LookupError):
    pass


class ConnectionCheck(ContractModel):
    key: Literal["reachable", "readOnly", "timeout", "rowLimit"]
    ok: bool


class LayoutColumn(ContractModel):
    name: str
    type: str
    role: ColumnRole | None


class SourceLayout(ContractModel):
    """The telemetry table as configured: columns with their roles and a few sample rows."""

    data_source_id: str
    table: str
    row_count: int | None
    columns: list[LayoutColumn]
    sample_rows: list[list[str]]
    is_simulated: bool


class DeviceKey(ContractModel):
    key_name: str
    rows: int | None


class StudioDevice(ContractModel):
    device_id: str
    dataset_id: str | None = None
    label: LocalizedText | None = None
    keys: list[DeviceKey]
    is_simulated: bool


class DeviceSuggestions(ContractModel):
    data_source_id: str
    device_id: str
    signals: list[SignalDefinition]
    mappings: list[SignalMapping]
    components: list[ComponentInstance]
    preview_window: TimeWindow | None
    is_simulated: bool


def _sources(request: Request) -> DataSourceRegistry:
    return request.app.state.sources


Sources = Annotated[DataSourceRegistry, Depends(_sources)]


def _read_only(adapter: TimeSeriesAdapter) -> bool:
    """Ask the database session itself, not just the configuration."""
    if not isinstance(adapter, SqlAdapter):
        return adapter.is_simulated  # the simulated adapter has no write path
    with adapter.connection() as conn:
        if conn.dialect.name == "postgresql":
            return conn.exec_driver_sql("SHOW transaction_read_only").scalar() == "on"
        return conn.exec_driver_sql("PRAGMA query_only").scalar() == 1


@router.get("/datasources/{data_source_id}/check", response_model=list[ConnectionCheck])
def check_source(data_source_id: str, _: Engineer, reg: Sources) -> list[ConnectionCheck]:
    config, adapter = reg.config(data_source_id), reg.adapter(data_source_id)
    try:
        adapter.discover()
        reachable, read_only = True, config.read_only and _read_only(adapter)
    except (AdapterError, SQLAlchemyError, OSError):
        reachable = read_only = False
    return [
        ConnectionCheck(key="reachable", ok=reachable),
        ConnectionCheck(key="readOnly", ok=read_only),
        ConnectionCheck(key="timeout", ok=config.statement_timeout_s <= MAX_TIMEOUT_S),
        ConnectionCheck(key="rowLimit", ok=config.max_rows <= MAX_ROWS),
    ]


@router.get("/datasources/{data_source_id}/layout", response_model=SourceLayout)
def source_layout(data_source_id: str, _: Engineer, reg: Sources) -> SourceLayout:
    adapter = reg.adapter(data_source_id)
    if isinstance(adapter, SqlAdapter):
        lay = adapter.layout
        roles: dict[str, ColumnRole] = {
            lay.device_column: "device",
            lay.key_column: "key",
            lay.time_column: "time",
        }
        roles.update({c: "value" for c in lay.value_columns})
        table = next(
            t
            for t in adapter.inspect_schema().tables
            if t.name == lay.table and (t.schema_name or None) in (lay.schema_name, None)
        )
        columns = [LayoutColumn(name=c.name, type=c.type, role=roles.get(c.name)) for c in table.columns]
        name, row_count = lay.table, None
    else:
        columns = [LayoutColumn(name=n, type=t, role=SIMULATED_ROLES.get(n)) for n, t, _ in RAW_COLUMNS]
        name = "raw_telemetry"
        counts = adapter.row_counts() if isinstance(adapter, SimulatedAdapter) else {}
        row_count = sum(counts.values()) if counts else None
    return SourceLayout(
        data_source_id=data_source_id,
        table=name,
        row_count=row_count,
        columns=columns,
        sample_rows=_samples(adapter, columns),
        is_simulated=adapter.is_simulated,
    )


def _samples(adapter: TimeSeriesAdapter, columns: list[LayoutColumn], n: int = 5) -> list[list[str]]:
    meta = adapter.discover()
    if not meta.devices or not meta.devices[0].key_names or meta.earliest_ts is None:
        return []
    device, key = meta.devices[0].device_id, meta.devices[0].key_names[0]
    window = TimeWindow(start=meta.earliest_ts, end=meta.earliest_ts + DEFAULT_PREVIEW)
    rows = adapter.query_range(device, key, window, n)
    cell = {
        "device": lambda r: r.device_id,
        "key": lambda r: r.key_name,
        "time": lambda r: r.ts.isoformat(),
        "value": lambda r: "" if r.value is None else repr(r.value),
    }
    return [[cell[c.role](r) if c.role else "" for c in columns] for r in rows]


@router.get("/datasources/{data_source_id}/devices", response_model=list[StudioDevice])
def source_devices(data_source_id: str, _: Viewer, reg: Sources) -> list[StudioDevice]:
    adapter = reg.adapter(data_source_id)
    counts = adapter.row_counts() if isinstance(adapter, SimulatedAdapter) else {}
    out = []
    for d in adapter.discover().devices:
        ds = reg.dataset_for(data_source_id, d.device_id)
        out.append(
            StudioDevice(
                device_id=d.device_id,
                dataset_id=ds.dataset_id if ds else None,
                label=ds.title if ds else None,
                keys=[DeviceKey(key_name=k, rows=counts.get((d.device_id, k))) for k in d.key_names],
                is_simulated=adapter.is_simulated,
            )
        )
    return out


@router.get("/datasources/{data_source_id}/devices/{device_id}/suggestions", response_model=DeviceSuggestions)
def device_suggestions(
    data_source_id: str, device_id: str, _: Viewer, reg: Sources, db: DB
) -> DeviceSuggestions:
    adapter = reg.adapter(data_source_id)
    meta = adapter.discover()
    if device_id not in {d.device_id for d in meta.devices}:
        raise UnknownDeviceError(f"device '{device_id}' not found in '{data_source_id}'")
    content = SignalConfigStore(db).current().content
    defined = {s.signal_id: s for s in content.signals}
    mappings = [m for m in content.mappings if (m.data_source_id, m.device_id) == (data_source_id, device_id)]
    signals = [defined[m.signal_id] for m in mappings]
    components: list[ComponentInstance] = []
    ds = reg.dataset_for(data_source_id, device_id)
    if ds:
        topo = ds.topology
        topo_signals = {s["signal_id"]: SignalDefinition.model_validate(s) for s in topo.get("signals", [])}
        used_keys, used_ids = {m.key_name for m in mappings}, {m.signal_id for m in mappings} | set(defined)
        for raw in topo.get("mappings", []):
            m = SignalMapping.model_validate({**raw, "data_source_id": data_source_id})
            if m.device_id == device_id and m.key_name not in used_keys and m.signal_id not in used_ids:
                mappings.append(m)
                signals.append(topo_signals[m.signal_id])
        machine = ds.machines.get(device_id)
        components = [
            ComponentInstance.model_validate(c)
            for c in topo.get("components", [])
            if c.get("machine_id") == machine
        ]
    window = ds.preview_window if ds and ds.preview_window else None
    if window is None and meta.latest_ts is not None:
        start = max(meta.latest_ts - DEFAULT_PREVIEW, meta.earliest_ts or meta.latest_ts)
        window = TimeWindow(start=start, end=meta.latest_ts + timedelta(seconds=1))
    return DeviceSuggestions(
        data_source_id=data_source_id,
        device_id=device_id,
        signals=signals,
        mappings=mappings,
        components=components,
        preview_window=window,
        is_simulated=adapter.is_simulated,
    )
