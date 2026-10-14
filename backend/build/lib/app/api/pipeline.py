"""Run the online feature/alarm pipeline for one machine (D-042). Needs an engineer."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.schemas import ContractModel
from app.core.security import Principal, Role, require
from app.decision.pipeline import PipelineResult, run_machine
from app.equipment.lifecycle import EquipmentStore

router = APIRouter(tags=["pipeline"])
DB = Annotated[Session, Depends(get_session)]
Engineer = Annotated[Principal, Depends(require(Role.ENGINEER))]


class PipelineRequest(ContractModel):
    machine_id: str
    until: datetime | None = Field(default=None, description="Process data up to this time (default: now)")


@router.post("/pipeline/run", response_model=PipelineResult)
def run(body: PipelineRequest, request: Request, _: Engineer, db: DB) -> PipelineResult:
    EquipmentStore(db).machine(body.machine_id)
    out = run_machine(db, request.app.state.sources, body.machine_id, body.until)
    db.commit()
    return out
