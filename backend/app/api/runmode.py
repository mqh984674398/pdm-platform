"""Run mode: which world the screens show, the simulation database or the production sources (D-053)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.runmode import RunMode, get_mode, set_mode
from app.core.schemas import ContractModel
from app.core.security import Principal, Role, require

router = APIRouter(tags=["settings"])
DB = Annotated[Session, Depends(get_session)]
Viewer = Annotated[Principal, Depends(require(Role.VIEWER))]
Admin = Annotated[Principal, Depends(require(Role.ADMIN))]


class RunModeState(ContractModel):
    mode: RunMode


@router.get("/run-mode", response_model=RunModeState)
def read_mode(_: Viewer, db: DB) -> RunModeState:
    return RunModeState(mode=get_mode(db))


@router.put("/run-mode", response_model=RunModeState)
def write_mode(body: RunModeState, who: Admin, db: DB) -> RunModeState:
    mode = set_mode(db, body.mode, who)
    db.commit()
    return RunModeState(mode=mode)
