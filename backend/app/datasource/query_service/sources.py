"""Configured data sources. Connection URLs are resolved server-side and never leave the server (SEC-03)."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from pathlib import Path

from app.datasource.adapter import TimeSeriesAdapter
from app.datasource.schemas import DataSourceConfig, SqlTableLayout
from app.datasource.simulated import SimulatedAdapter
from app.datasource.sql import AdapterError, SqlAdapter

SECRET_REF = re.compile(r"^secret://pdm/([a-z0-9][a-z0-9-]{0,62})$")


class UnknownSourceError(AdapterError):
    pass


def env_secret(credential_ref: str) -> str:
    """``secret://pdm/<name>`` → environment variable ``PDM_SECRET_<NAME>`` (dashes become underscores)."""
    m = SECRET_REF.match(credential_ref)
    if not m:
        raise AdapterError("credential_ref must look like secret://pdm/<name>")
    var = "PDM_SECRET_" + m.group(1).upper().replace("-", "_")
    value = os.environ.get(var)
    if not value:
        raise AdapterError(f"secret {credential_ref} is not configured on the server")
    return value


class DataSourceRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, tuple[DataSourceConfig, TimeSeriesAdapter]] = {}

    def add(self, config: DataSourceConfig, adapter: TimeSeriesAdapter) -> None:
        if config.data_source_id != adapter.data_source_id:
            raise ValueError("config and adapter disagree on data_source_id")
        self._sources[config.data_source_id] = (config, adapter)

    def configs(self) -> list[DataSourceConfig]:
        return [c for c, _ in self._sources.values()]

    def config(self, data_source_id: str) -> DataSourceConfig:
        return self._entry(data_source_id)[0]

    def adapter(self, data_source_id: str) -> TimeSeriesAdapter:
        return self._entry(data_source_id)[1]

    def _entry(self, data_source_id: str) -> tuple[DataSourceConfig, TimeSeriesAdapter]:
        try:
            return self._sources[data_source_id]
        except KeyError as exc:
            raise UnknownSourceError(f"unknown data source '{data_source_id}'") from exc

    @classmethod
    def from_file(cls, path: Path, resolve: Callable[[str], str] = env_secret) -> DataSourceRegistry:
        """Load ``[{"config": ..., "layout": ...} | {"config": ..., "simulated_dataset": "<dir>"}]``."""
        reg = cls()
        for item in json.loads(path.read_text(encoding="utf-8")):
            config = DataSourceConfig.model_validate(item["config"])
            if "simulated_dataset" in item:
                dataset = (path.parent / item["simulated_dataset"]).resolve()
                reg.add(config, SimulatedAdapter(dataset, data_source_id=config.data_source_id))
            else:
                if not config.credential_ref:
                    raise AdapterError(f"{config.data_source_id}: SQL sources need a credential_ref")
                layout = SqlTableLayout.model_validate(item["layout"])
                reg.add(config, SqlAdapter(config, layout, resolve(config.credential_ref)))
        return reg
