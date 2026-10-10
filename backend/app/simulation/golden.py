"""Scenario metadata and Golden Case contracts (SIM-03, SIM-04, TST-02).

Golden Cases state what a correct monitoring pipeline must conclude for a simulated scenario.
They are regression expectations for simulated data only, never evidence of real-world accuracy.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field, model_validator

from app.core.schemas import ContractModel, LocalizedText
from app.decision.schemas import HealthState
from app.equipment.schemas import MaintenanceWorkflowState
from app.prediction.schemas import UnsupportedReason
from app.signals.schemas import QualityFlag

DATA_DIR = Path(__file__).resolve().parents[3] / "Data"


class Expectation(ContractModel):
    """What must hold for one component during [start_h, end_h) hours since scenario start."""

    start_h: float = Field(ge=0)
    end_h: float
    allowed_health: list[HealthState] = Field(min_length=1)
    required_flags: list[QualityFlag] = Field(default_factory=list)
    must_abstain: UnsupportedReason | None = None
    workflow: list[MaintenanceWorkflowState] | None = Field(
        default=None, description="Expected maintenance workflow path for an event in this interval"
    )
    note: LocalizedText

    @model_validator(mode="after")
    def _consistent(self) -> Expectation:
        if self.end_h <= self.start_h:
            raise ValueError("end_h must be after start_h")
        if self.must_abstain is not None and HealthState.UNKNOWN not in self.allowed_health:
            raise ValueError("an abstention interval must allow UNKNOWN health")
        return self


class GoldenCase(ContractModel):
    case_id: str = Field(pattern=r"^GC-S\d{2}-\d{2}$")
    scenario_id: str = Field(pattern=r"^S\d{2}$")
    component_id: str
    signal_ids: list[str] = Field(min_length=1)
    title: LocalizedText
    expectations: list[Expectation] = Field(min_length=1)


class ScenarioMeta(ContractModel):
    scenario_id: str = Field(pattern=r"^S\d{2}$")
    slug: str
    title: LocalizedText
    seed: int
    dataset_id: str
    is_simulated: bool = True
    known_regimes: list[str]
    expected_observable_behavior: LocalizedText
    ground_truth: LocalizedText
    expected_health_response: LocalizedText
    abstention_cases: list[LocalizedText]
    limitations: list[LocalizedText] = Field(default_factory=list)
    golden_case_ids: list[str] = Field(min_length=1)


def load_golden_cases(data_dir: Path = DATA_DIR) -> list[GoldenCase]:
    raw = json.loads((data_dir / "golden_cases" / "index.json").read_text(encoding="utf-8"))
    return [GoldenCase.model_validate(c) for c in raw["cases"]]


def load_scenarios(data_dir: Path = DATA_DIR) -> list[ScenarioMeta]:
    return [
        ScenarioMeta.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted((data_dir / "scenarios").glob("S*/scenario.json"))
    ]


def scenario_dir(scenario_id: str, data_dir: Path = DATA_DIR) -> Path:
    (match,) = (data_dir / "scenarios").glob(f"{scenario_id}_*")
    return match
