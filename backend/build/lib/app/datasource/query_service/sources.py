"""Configured data sources. Connection URLs are resolved server-side and never leave the server (SEC-03)."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.schemas import LocalizedText, TimeWindow
from app.core.security import Principal, Role
from app.datasource.adapter import TimeSeriesAdapter
from app.datasource.schemas import DataSourceConfig, DataSourceKind, SqlTableLayout
from app.datasource.simulated import SimulatedAdapter
from app.datasource.sql import AdapterError, SqlAdapter
from app.datasource.tdengine import TdengineAdapter, TdengineLayout

SECRET_REF = re.compile(r"^secret://pdm/([a-z0-9][a-z0-9-]{0,62})$")


class UnknownSourceError(AdapterError):
    pass


class SourceAccessError(AdapterError):
    """The user's role may not use this data source (D-035)."""


def may_use(config: DataSourceConfig, principal: Principal) -> bool:
    return config.kind != DataSourceKind.SIMULATED or principal.role == Role.ADMIN


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


@dataclass(frozen=True)
class SimulatedDataset:
    """A simulator dataset behind a simulated source, with what the Studio needs to describe it.

    ``topology`` is the dataset's ``topology.json`` (suggested signals, mappings, components);
    ``preview_window`` is an optional configured default window for previews.
    """

    directory: Path
    dataset_id: str
    title: LocalizedText | None
    machines: dict[str, str]  # device id -> machine id
    topology: dict[str, Any] = field(default_factory=dict)
    preview_window: TimeWindow | None = None

    @classmethod
    def load(cls, directory: Path, preview_window: TimeWindow | None = None) -> SimulatedDataset:
        def read(name: str) -> dict[str, Any]:
            path = directory / name
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

        scenario, topology, config = read("scenario.json"), read("topology.json"), read("config.json")
        return cls(
            directory=directory,
            dataset_id=scenario.get("scenario_id") or directory.name,
            title=LocalizedText.model_validate(scenario["title"]) if "title" in scenario else None,
            machines={m["device_id"]: m["machine_id"] for m in config.get("machines", [])},
            topology=topology,
            preview_window=preview_window,
        )


class DataSourceRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, tuple[DataSourceConfig, TimeSeriesAdapter]] = {}
        self._datasets: dict[str, list[SimulatedDataset]] = {}
        self.skipped: list[str] = []  # sources not loaded because production data is not approved

    def add(
        self,
        config: DataSourceConfig,
        adapter: TimeSeriesAdapter,
        datasets: Sequence[SimulatedDataset] = (),
    ) -> None:
        if config.data_source_id != adapter.data_source_id:
            raise ValueError("config and adapter disagree on data_source_id")
        self._sources[config.data_source_id] = (config, adapter)
        self._datasets[config.data_source_id] = list(datasets)

    def remove(self, data_source_id: str) -> None:
        self._sources.pop(data_source_id, None)
        self._datasets.pop(data_source_id, None)

    def datasets(self, data_source_id: str) -> list[SimulatedDataset]:
        return list(self._datasets.get(data_source_id, []))

    def dataset_for(self, data_source_id: str, device_id: str) -> SimulatedDataset | None:
        """The simulated dataset that holds ``device_id``; None for real sources."""
        return next((d for d in self._datasets.get(data_source_id, []) if device_id in d.machines), None)

    def configs(self) -> list[DataSourceConfig]:
        return [c for c, _ in self._sources.values()]

    def configs_for(self, principal: Principal) -> list[DataSourceConfig]:
        """Sources this user may work with: the simulation database is for administrators (D-035)."""
        return [c for c in self.configs() if may_use(c, principal)]

    def require_access(self, data_source_id: str, principal: Principal) -> None:
        if not may_use(self.config(data_source_id), principal):
            raise SourceAccessError(
                f"data source '{data_source_id}' is the simulation database, available to administrators only"
            )

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
    def from_file(
        cls, path: Path, resolve: Callable[[str], str] = env_secret, allow_production: bool = True
    ) -> DataSourceRegistry:
        """Load a JSON list of sources. Each item is ``{"config": ..., "layout": ...}`` for SQL, or
        ``{"config": ..., "simulated_dataset": "<dir>"}`` / ``{"config": ..., "simulated_datasets":
        [{"dir": "<dir>", "preview_window": {"start": ..., "end": ...}}]}`` for simulated data.
        Relative directories resolve against the file's folder. With ``allow_production=False``
        (SEC-06, until the user approves) generic SQL sources are skipped and listed in ``skipped``.
        TDengine sources (``"tdengine_layout": ...``) load without that approval: they are production
        sources read through a read-only account, which the owner allowed directly (D-035)."""
        reg = cls()
        for item in json.loads(path.read_text(encoding="utf-8")):
            config = DataSourceConfig.model_validate(item["config"])
            if config.kind == DataSourceKind.TDENGINE:
                if config.is_simulated:
                    raise AdapterError(f"{config.data_source_id}: TDengine sources are production sources")
                if not config.credential_ref:
                    raise AdapterError(f"{config.data_source_id}: TDengine sources need a credential_ref")
                adapter = TdengineAdapter(
                    config,
                    TdengineLayout.model_validate(item["tdengine_layout"]),
                    resolve(config.credential_ref),
                    scheme=item.get("scheme", "http"),
                )
                reg.add(config, adapter)
                continue
            if not allow_production and not (config.is_simulated and config.kind == DataSourceKind.SIMULATED):
                reg.skipped.append(config.data_source_id)
                continue
            entries = item.get("simulated_datasets")
            if entries is None and "simulated_dataset" in item:
                entries = [{"dir": item["simulated_dataset"]}]
            if entries is not None:
                datasets = [
                    SimulatedDataset.load(
                        (path.parent / e["dir"]).resolve(),
                        TimeWindow.model_validate(e["preview_window"]) if e.get("preview_window") else None,
                    )
                    for e in entries
                ]
                adapter = SimulatedAdapter(
                    [d.directory for d in datasets], data_source_id=config.data_source_id
                )
                reg.add(config, adapter, datasets)
            else:
                if not config.credential_ref:
                    raise AdapterError(f"{config.data_source_id}: SQL sources need a credential_ref")
                layout = SqlTableLayout.model_validate(item["layout"])
                reg.add(config, SqlAdapter(config, layout, resolve(config.credential_ref)))
        return reg
