"""L1 contracts: data sources, query templates, raw telemetry."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field

from app.core.schemas import ContractModel, LocalizedText


class DataSourceKind(StrEnum):
    SQL = "SQL"
    SIMULATED = "SIMULATED"


class DataSourceConfig(ContractModel):
    """Connection configuration as exposed through the API.

    Credentials are never part of this schema (SEC-03): ``credential_ref`` names a server-side secret.
    """

    data_source_id: str
    name: str
    kind: DataSourceKind
    engine: str | None = Field(default=None, description="Verified DB engine, e.g. 'postgresql', 'mysql'")
    host: str | None = None
    port: int | None = Field(default=None, gt=0, lt=65536)
    database: str | None = None
    credential_ref: str | None = None
    read_only: bool = True
    statement_timeout_s: float = Field(default=30, gt=0, le=300)
    max_rows: int = Field(default=200_000, gt=0, le=2_000_000)
    is_simulated: bool


class QueryParamType(StrEnum):
    STRING = "STRING"
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    TIMESTAMP = "TIMESTAMP"
    IDENTIFIER = "IDENTIFIER"  # must match discovered metadata allowlist


class QueryParameter(ContractModel):
    name: str = Field(pattern=r"^[a-z_][a-z0-9_]*$")
    type: QueryParamType
    label: LocalizedText
    required: bool = True


class QueryTemplate(ContractModel):
    """An approved, parameterized, read-only query (L1-05). SQL text is visible to admins only."""

    template_id: str
    name: LocalizedText
    description: LocalizedText
    data_source_id: str
    parameters: list[QueryParameter]
    max_rows: int = Field(gt=0, le=2_000_000)
    max_range_hours: float = Field(gt=0)
    version: int = Field(ge=1)


class RawTelemetryRow(ContractModel):
    """One row as returned by the source, before semantic mapping (ARCHITECTURE §4 layer 1)."""

    device_id: str
    key_name: str
    ts: AwareDatetime
    value: float | None
    source_ref: str = Field(description="Data source id plus template/version that produced the row")
    is_simulated: bool


class DeviceKeys(ContractModel):
    device_id: str
    key_names: list[str]


class SourceMetadata(ContractModel):
    """Result of read-only metadata discovery (L1-04)."""

    data_source_id: str
    devices: list[DeviceKeys]
    earliest_ts: AwareDatetime | None
    latest_ts: AwareDatetime | None
    is_simulated: bool


class ColumnInfo(ContractModel):
    name: str
    type: str = Field(description="Type as reported by the database driver")
    nullable: bool


class TableInfo(ContractModel):
    schema_name: str | None
    name: str
    columns: list[ColumnInfo]


class SourceSchema(ContractModel):
    """Read-only structural discovery: schemas, tables, columns (L1-04)."""

    data_source_id: str
    engine: str = Field(description="Engine reported by the live connection, e.g. 'postgresql'")
    server_version: str | None = None
    tables: list[TableInfo]
    is_simulated: bool


class SqlTableLayout(ContractModel):
    """Where telemetry lives in a SQL source. Configured per source, never assumed (L1-08).

    ``value_columns`` are read in order and the first non-null one is the value, which covers
    sources that split values by type (e.g. ``value_double`` and ``value_long``).
    """

    schema_name: str | None = None
    table: str
    device_column: str
    key_column: str
    time_column: str
    value_columns: list[str] = Field(min_length=1)
    naive_time_zone: str = Field(
        default="UTC", description="Zone for timestamp columns without time zone; verify against the source"
    )
    verified: bool = Field(
        default=False, description="True only after the layout was checked against the real database"
    )
