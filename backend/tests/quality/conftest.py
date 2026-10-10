"""Quality fixtures: one simulated source per scenario, with the scenario's own signal topology."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from functools import cache
from pathlib import Path

from app.core.schemas import TimeWindow
from app.datasource.query_service.sources import DataSourceRegistry
from app.datasource.schemas import DataSourceConfig, DataSourceKind
from app.datasource.simulated import SimulatedAdapter
from app.monitoring.quality.service import quality_report
from app.monitoring.schemas import QualityRequest, QualityResponse
from app.signals.schemas import QualityFlag, SignalConfig

DATA = Path(__file__).resolve().parents[3] / "Data"
GOLDEN = json.loads((DATA / "golden_cases" / "index.json").read_text(encoding="utf-8"))["cases"]


class Scenario:
    def __init__(self, sid: str):
        self.dir = next((DATA / "scenarios").glob(f"{sid}_*"))
        topo = json.loads((self.dir / "topology.json").read_text(encoding="utf-8"))
        cfg = json.loads((self.dir / "config.json").read_text(encoding="utf-8"))
        self.t0 = datetime.fromisoformat(cfg["start"].replace("Z", "+00:00"))
        self.hours = float(cfg["duration_hours"])
        self.device = cfg["machines"][0]["device_id"]
        self.config = SignalConfig(signals=topo["signals"], mappings=topo["mappings"])
        self.sources = DataSourceRegistry()
        source = DataSourceConfig(data_source_id="simulated", name=sid, kind=DataSourceKind.SIMULATED,
                                  read_only=True, is_simulated=True)  # fmt: skip
        self.sources.add(source, SimulatedAdapter(self.dir))

    def window(self, start_h: float, end_h: float) -> TimeWindow:
        return TimeWindow(start=self.t0 + timedelta(hours=start_h), end=self.t0 + timedelta(hours=end_h))

    def report(self, signal_ids: list[str], start_h: float, end_h: float, **kw) -> QualityResponse:
        req = QualityRequest(signal_ids=signal_ids, window=self.window(start_h, end_h), **kw)
        return quality_report(self.sources, self.config, req)


@cache
def scenario(sid: str) -> Scenario:
    return Scenario(sid)


def all_flags(resp: QualityResponse) -> set[QualityFlag]:
    return {f for r in resp.reports for f in r.flags} | {f for a in resp.alignment for f in a.flags}
