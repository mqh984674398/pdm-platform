"""Replay-based parameter optimization (T025, UI-10): run champion vs candidates, read the latest run.

Running needs engineer; reading needs viewer. A run only recommends a challenger; nothing is promoted.
Without a regression suite (no Golden Cases for the components) a run is refused.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.schemas import ContractModel, LocalizedText
from app.core.security import Principal, Role, require
from app.optimization.schemas import OptimizationRun
from app.optimization.service import OptimizationService, latest
from app.optimization.suite import demo_suite

router = APIRouter(tags=["optimization"])
DB = Annotated[Session, Depends(get_session)]
Viewer = Annotated[Principal, Depends(require(Role.VIEWER))]
Engineer = Annotated[Principal, Depends(require(Role.ENGINEER))]
DATA = Path(__file__).resolve().parents[3] / "Data"


class RunRequest(ContractModel):
    candidates: int = Field(default=12, ge=1, le=40)
    seed: int = Field(default=0, ge=0)


class OptimizationReadiness(ContractModel):
    """What a comparison run would replay, and why it cannot run when it cannot."""

    can_run: bool
    suite: str | None
    cases: int
    components: int
    stored_windows: int = Field(description="Stored feature windows of those components")
    is_simulated: bool
    reason: LocalizedText | None = None


@router.get("/optimization/readiness", response_model=OptimizationReadiness)
def readiness(_: Viewer, db: DB) -> OptimizationReadiness:
    from app.monitoring.features.store import FeatureStore

    try:
        suite = demo_suite(db, DATA)
    except OSError:
        suite = None
    cases = suite.cases if suite else ()
    comps = {c.component_id for c in cases}
    windows = sum(len(FeatureStore(db).vectors(c)) for c in comps)
    reason = None
    if not cases:
        reason = LocalizedText(
            zh="没有可回放的回归用例（Golden Case）。内置用例只覆盖仿真演示设备；"
            "现场部件需要工程师先编写 Golden Case，才能比较参数。",
            en="No regression cases (Golden Cases) to replay. The built-in cases cover the simulated demo "
            "machines only; plant components need engineer-written Golden Cases first.",
        )
    elif not windows:
        reason = LocalizedText(
            zh="这些部件还没有已存储的特征窗口，回放没有数据。",
            en="Those components have no stored feature windows yet, so there is nothing to replay.",
        )
    return OptimizationReadiness(
        can_run=bool(cases and windows),
        suite=suite.name if suite else None,
        cases=len(cases),
        components=len(comps),
        stored_windows=windows,
        is_simulated=bool(suite and suite.is_simulated),
        reason=reason,
    )


@router.post("/optimization/runs", response_model=OptimizationRun)
def start_run(body: RunRequest, who: Engineer, db: DB) -> OptimizationRun:
    return OptimizationService(db, demo_suite(db, DATA)).run(who, body.candidates, body.seed)


@router.get("/optimization/runs/latest", response_model=OptimizationRun)
def latest_run(_: Viewer) -> OptimizationRun:
    return latest()
