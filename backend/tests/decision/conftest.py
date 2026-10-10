"""Replay SIMULATED demo machines through the real pipeline once per module for golden-case checks."""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.main  # noqa: F401  (registers tables)
from app.core.db import Base
from app.datasource.query_service.sources import DataSourceRegistry
from app.decision.fleet import FleetHealthService
from app.simulation.demo_pipeline import DEMO_FLEET, add_demo_source, demo_machines, run_pipeline
from app.simulation.golden import DATA_DIR

SCENARIOS = ("S01", "S03", "S04", "S07", "S11", "S19")


@pytest.fixture(scope="module")
def replay(tmp_path_factory):
    machines = demo_machines(DATA_DIR, [row for row in DEMO_FLEET if row[1] in SCENARIOS])
    sources = DataSourceRegistry()
    add_demo_source(sources, machines)
    engine = create_engine(f"sqlite:///{tmp_path_factory.mktemp('dec')}/d.db")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        run_pipeline(s, sources, machines)
        yield FleetHealthService(s), machines
    engine.dispose()


def golden() -> list[dict]:
    return json.loads((DATA_DIR / "golden_cases" / "index.json").read_text(encoding="utf-8"))["cases"]


def graded(svc, machines, scenario: str):
    """(case, expectation, [fused level per window in the span]) for one scenario."""
    m = next(x for x in machines if x.scenario_id == scenario)
    out = []
    for case in (c for c in golden() if c["scenario_id"] == scenario):
        cid = case["component_id"].replace("M01-", f"{m.machine_id}-")
        results = svc.window_decisions(cid)
        for exp in case["expectations"]:
            if exp.get("must_abstain"):
                continue
            span = [
                r
                for r in results
                if exp["start_h"]
                <= (r.decision.meta.data_window.start - m.t0).total_seconds() / 3600
                < exp["end_h"]
            ]
            out.append((case, exp, span))
    return out
