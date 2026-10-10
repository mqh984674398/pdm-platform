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
from app.core.schemas import ContractModel
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


@router.post("/optimization/runs", response_model=OptimizationRun)
def start_run(body: RunRequest, who: Engineer, db: DB) -> OptimizationRun:
    return OptimizationService(db, demo_suite(db, DATA)).run(who, body.candidates, body.seed)


@router.get("/optimization/runs/latest", response_model=OptimizationRun)
def latest_run(_: Viewer) -> OptimizationRun:
    return latest()
