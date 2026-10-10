"""Labeled SIMULATED feature windows for model training (T022).

Each scenario is replayed like the demo pipeline (regime catalog from the first days, features for
the rest, scaled for sparse scenarios) and every feature window gets its label from the scenario's
ground truth row for the same component and window.
"""

from __future__ import annotations

import csv
import gzip
from datetime import datetime
from functools import cache
from pathlib import Path

from app.datasource.query_service.sources import DataSourceRegistry
from app.equipment.regimes import learn_catalog
from app.equipment.schemas import ComponentType
from app.equipment.state import load_series
from app.monitoring.features.extract import extract_features
from app.prediction.models.dataset import Sample
from app.prediction.models.labels import label
from app.simulation.demo_pipeline import CATALOG_H, add_demo_source, load_machine


def _ts(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


@cache
def scenario_samples(data_dir: Path, scenario_id: str) -> tuple[Sample, ...]:
    m = load_machine(data_dir, "M01", scenario_id, scenario_id, scenario_id)
    sources = DataSourceRegistry()
    add_demo_source(sources, [m])
    series = load_series(sources, m.items, m.window(0, m.hours))
    catalog_h = CATALOG_H * m.scale
    catalog = learn_catalog(series, "M01", m.window(0, catalog_h), f"{scenario_id}-ref")
    types = {c["component_id"]: ComponentType(c["type"]) for c in m.topology["components"]}
    lifecycles = {
        cid: [
            (lc["lifecycle_id"], _ts(lc["installed_at"]), _ts(lc["retired_at"]) if lc["retired_at"] else None)
            for lc in m.topology["lifecycles"]
            if lc["component_id"] == cid
        ]
        for cid in types
    }
    windows = [(_ts(e["performed_at"]), _ts(e["performed_at"]), e["event_id"]) for e in m.events]
    extraction = extract_features(series, m.window(catalog_h, m.hours), types, lifecycles, catalog, windows)
    with gzip.open(m.dir / "truth_components.csv.gz", "rt", encoding="utf-8") as f:
        truth = {(r["component_id"], _ts(r["window_start"]).replace(second=0)): r for r in csv.DictReader(f)}
    out = []
    for v in extraction.vectors:
        row = truth.get((v.component_id, v.window.start.replace(second=0, microsecond=0)))
        y = label(types[v.component_id], row) if row else None
        if y is not None:
            hours = (v.window.start - m.t0).total_seconds() / 3600
            out.append(Sample(vector=v, label=y, scenario=scenario_id, hours=hours))
    return tuple(out)
