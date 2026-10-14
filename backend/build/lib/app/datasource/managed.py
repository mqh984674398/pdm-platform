"""Data sources an administrator manages in the application (D-044).

Only TDengine sources can be managed here: they are read-only production sources. Connection settings
live in the database; the account is the one secret and stays out of it: it goes to the server's
protected ``.env`` as ``PDM_SECRET_<ID>`` (``<user>:<password>``) and is never returned by the API (SEC-03).
Sources from the datasources file stay file-managed and cannot be edited here.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import Field
from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base
from app.core.schemas import ContractModel
from app.datasource.query_service.sources import DataSourceRegistry, env_secret
from app.datasource.schemas import DataSourceConfig, DataSourceKind
from app.datasource.sql import AdapterError
from app.datasource.tdengine import TdengineAdapter, TdengineLayout

ID = r"^[a-z0-9][a-z0-9-]{0,62}$"
TRANSPORT: httpx.BaseTransport | None = None  # tests inject a fake TDengine server here


class ManagedSourceRecord(Base):
    __tablename__ = "managed_datasources"

    data_source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    layout: Mapped[dict] = mapped_column(JSON, nullable=False)
    scheme: Mapped[str] = mapped_column(String(8), nullable=False, default="http")
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ManagedSourceBody(ContractModel):
    """Write model. ``user`` and ``password`` are write-only: leave both empty to keep the stored account."""

    data_source_id: str = Field(pattern=ID)
    name: str = Field(min_length=1, max_length=120)
    host: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._-]+$")
    port: int = Field(default=6041, gt=0, lt=65536)
    database: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    scheme: str = Field(default="http", pattern=r"^https?$")
    user: str | None = Field(default=None, max_length=64, pattern=r"^[^:\r\n]+$")
    password: str | None = Field(default=None, max_length=128, pattern=r"^[^\r\n]+$")
    stable: str
    device_tag: str
    time_column: str = "ts"
    key_column: str | None = None
    value_columns: list[str] = Field(default_factory=list)
    naive_time_zone: str = "UTC"
    statement_timeout_s: float = Field(default=30, gt=0, le=300)
    max_rows: int = Field(default=200_000, gt=0, le=2_000_000)


class ManagedSource(ContractModel):
    data_source_id: str
    name: str
    kind: DataSourceKind
    host: str | None
    port: int | None
    database: str | None
    scheme: str | None
    layout: TdengineLayout | None
    managed: bool = Field(description="True when it can be edited here; file-defined sources cannot")
    credential_set: bool = Field(description="Whether a server-side account is configured (never its value)")
    active: bool = Field(description="Whether the source is loaded and usable now")
    is_simulated: bool


def secret_var(data_source_id: str) -> str:
    return "PDM_SECRET_" + data_source_id.upper().replace("-", "_")


def credential_ref(data_source_id: str) -> str:
    return f"secret://pdm/{data_source_id}"


def write_secret(env_path: Path, data_source_id: str, user: str, password: str) -> None:
    """Set ``PDM_SECRET_<ID>`` in the protected .env (rewritten in place so its permissions stay) and in
    this process, so the source works without a restart."""
    var, line = secret_var(data_source_id), f"{secret_var(data_source_id)}={user}:{password}"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    lines = [x for x in lines if not re.match(rf"^{re.escape(var)}=", x)] + [line]
    with env_path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    os.environ[var] = f"{user}:{password}"


def remove_secret(env_path: Path, data_source_id: str) -> None:
    var = secret_var(data_source_id)
    if env_path.exists():
        kept = [x for x in env_path.read_text(encoding="utf-8").splitlines() if not x.startswith(f"{var}=")]
        with env_path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(kept) + "\n")
    os.environ.pop(var, None)


def config_of(body: ManagedSourceBody) -> DataSourceConfig:
    return DataSourceConfig(
        data_source_id=body.data_source_id,
        name=body.name,
        kind=DataSourceKind.TDENGINE,
        engine="tdengine",
        host=body.host,
        port=body.port,
        database=body.database,
        credential_ref=credential_ref(body.data_source_id),
        read_only=True,
        statement_timeout_s=body.statement_timeout_s,
        max_rows=body.max_rows,
        is_simulated=False,
    )


def layout_of(body: ManagedSourceBody, verified: bool = False) -> TdengineLayout:
    return TdengineLayout(
        stable=body.stable,
        device_tag=body.device_tag,
        time_column=body.time_column,
        key_column=body.key_column,
        value_columns=body.value_columns,
        naive_time_zone=body.naive_time_zone,
        verified=verified,
    )


def build(rec: ManagedSourceRecord) -> tuple[DataSourceConfig, TdengineAdapter]:
    """Raises AdapterError when the account is not configured on the server."""
    config = DataSourceConfig.model_validate(rec.config)
    adapter = TdengineAdapter(
        config,
        TdengineLayout.model_validate(rec.layout),
        env_secret(config.credential_ref or ""),
        scheme=rec.scheme,
        transport=TRANSPORT,
    )
    return config, adapter


def load_managed(session: Session, registry: DataSourceRegistry) -> list[str]:
    """Load every stored source into the registry; returns ids that could not be loaded (no account yet)."""
    inactive = []
    for rec in session.query(ManagedSourceRecord).order_by(ManagedSourceRecord.data_source_id):
        try:
            registry.add(*build(rec))
        except AdapterError:
            inactive.append(rec.data_source_id)
    return inactive


def stamp() -> datetime:
    return datetime.now(UTC)
