"""Regression suite for replay: Golden Case expectations mapped onto components (TST-02).

The demo suite maps the SIMULATED demo fleet (one scenario per machine) onto its Golden Cases. A real
plant has no Golden Cases until engineers write them; without a suite, optimization is refused.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.equipment.lifecycle import EquipmentStore


@dataclass(frozen=True)
class Expectation:
    start_h: float
    end_h: float
    allowed: tuple[str, ...]


@dataclass(frozen=True)
class RegressionCase:
    case_id: str
    component_id: str
    t0: datetime
    expectations: tuple[Expectation, ...]


@dataclass(frozen=True)
class RegressionSuite:
    name: str
    cases: tuple[RegressionCase, ...]
    is_simulated: bool


def demo_suite(session: Session, data_dir: Path) -> RegressionSuite:
    from app.simulation.demo_pipeline import DEMO_FLEET, load_machine

    present = {m.machine_id for m in EquipmentStore(session).machines()}
    golden = json.loads((data_dir / "golden_cases" / "index.json").read_text(encoding="utf-8"))["cases"]
    cases = []
    for row in DEMO_FLEET:
        if row[0] not in present:
            continue
        m = load_machine(data_dir, *row)
        for c in (c for c in golden if c["scenario_id"] == m.scenario_id):
            exps = tuple(
                Expectation(e["start_h"], e["end_h"], tuple(e["allowed_health"]))
                for e in c["expectations"]
                if not e.get("must_abstain")
            )
            cases.append(
                RegressionCase(
                    c["case_id"], c["component_id"].replace("M01-", f"{m.machine_id}-"), m.t0, exps
                )
            )
    return RegressionSuite("golden-cases (SIMULATED demo fleet)", tuple(cases), True)
