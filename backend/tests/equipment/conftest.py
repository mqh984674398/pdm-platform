"""Equipment fixtures: one simulated source per scenario, with the scenario's topology and truth."""

from __future__ import annotations

import csv
import gzip
import json
from datetime import datetime, timedelta
from functools import cache
from pathlib import Path

from app.core.schemas import TimeWindow
from app.datasource.query_service.sources import DataSourceRegistry
from app.datasource.schemas import DataSourceConfig, DataSourceKind
from app.datasource.simulated import SimulatedAdapter
from app.equipment.state import Series, load_series
from app.signals.schemas import SignalDefinition, SignalMapping

DATA = Path(__file__).resolve().parents[3] / "Data"
GOLDEN = json.loads((DATA / "golden_cases" / "index.json").read_text(encoding="utf-8"))["cases"]


def _ts(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


class Scenario:
    def __init__(self, sid: str):
        self.dir = next((DATA / "scenarios").glob(f"{sid}_*"))
        self.topology = json.loads((self.dir / "topology.json").read_text(encoding="utf-8"))
        self.cfg = json.loads((self.dir / "config.json").read_text(encoding="utf-8"))
        self.faults = json.loads((self.dir / "faults.json").read_text(encoding="utf-8"))
        self.t0 = _ts(self.cfg["start"])
        self.hours = float(self.cfg["duration_hours"])
        self.machine = self.cfg["machines"][0]["machine_id"]
        self.sources = DataSourceRegistry()
        source = DataSourceConfig(
            data_source_id="simulated",
            name=sid,
            kind=DataSourceKind.SIMULATED,
            read_only=True,
            is_simulated=True,
        )
        self.sources.add(source, SimulatedAdapter(self.dir))
        signals = {s["signal_id"]: SignalDefinition(**s) for s in self.topology["signals"]}
        self.items = [(SignalMapping(**m), signals[m["signal_id"]]) for m in self.topology["mappings"]]
        with gzip.open(self.dir / "truth_windows.csv.gz", "rt", encoding="utf-8") as f:
            self.truth = list(csv.DictReader(f))

    def window(self, start_h: float, end_h: float) -> TimeWindow:
        return TimeWindow(start=self.t0 + timedelta(hours=start_h), end=self.t0 + timedelta(hours=end_h))

    def hours_of(self, ts: datetime) -> float:
        return (ts - self.t0).total_seconds() / 3600

    def lifecycles(self) -> dict[str, str]:
        return {
            lc["component_id"]: lc["lifecycle_id"]
            for lc in self.topology["lifecycles"]
            if lc["status"] == "ACTIVE"
        }

    def maintenance(self) -> list[tuple[datetime, datetime, str]]:
        out = []
        for i, m in enumerate(self.cfg.get("maintenance", [])):
            a = self.t0 + timedelta(hours=m["at_h"])
            out.append((a, a + timedelta(hours=m["duration_h"]), f"sim-maint-{i}"))
        return out


@cache
def scenario(sid: str) -> Scenario:
    return Scenario(sid)


@cache
def series(sid: str) -> list[Series]:
    sc = scenario(sid)
    return load_series(sc.sources, sc.items, sc.window(0, sc.hours))
