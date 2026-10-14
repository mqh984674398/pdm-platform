"""Contracts for replay-based champion/challenger evaluation (T025)."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, Field

from app.core.schemas import ContractModel


class CaseScore(ContractModel):
    case_id: str
    component_id: str
    windows: int
    within: int
    over: int = Field(description="Windows above the highest allowed level (false escalation)")
    under: int = Field(description="Windows below the lowest allowed level (missed or late detection)")


class ReplayMetrics(ContractModel):
    windows: int
    within: int
    over: int
    under: int
    ratio: float
    cases: list[CaseScore]


class CandidateResult(ContractModel):
    candidate_id: str
    path: Literal["champion", "A", "B"]
    changes: dict[str, float]
    rules_version: str
    policy_version: str
    safety_unchanged: bool
    metrics: ReplayMetrics


class OptimizationRun(ContractModel):
    run_id: str
    started_by: str
    started_at: AwareDatetime
    seed: int
    suite: str
    champion: CandidateResult
    candidates: list[CandidateResult]
    recommended: str | None = Field(
        description="Best challenger that beats the champion without more missed windows; never promoted here"
    )
    is_simulated: bool
