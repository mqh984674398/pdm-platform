"""Dashboard aggregation (T020): fleet health overview and a component's health evidence trail.

Reads only; both need viewer. Health is computed on request from stored features, verified
references and the current rule settings; nothing is stored as a health label.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.security import Principal, Role, require
from app.decision.fleet import FleetHealthService
from app.decision.schemas import ComponentHealthReport, FleetOverview

router = APIRouter(tags=["fleet"])
DB = Annotated[Session, Depends(get_session)]
Viewer = Annotated[Principal, Depends(require(Role.VIEWER))]


@router.get("/fleet", response_model=FleetOverview)
def fleet_overview(_: Viewer, db: DB) -> FleetOverview:
    return FleetHealthService(db).overview()


@router.get("/components/{component_id}/health", response_model=ComponentHealthReport)
def component_health(component_id: str, _: Viewer, db: DB) -> ComponentHealthReport:
    return FleetHealthService(db).report(component_id)
