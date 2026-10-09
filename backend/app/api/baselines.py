"""Baselines and degradation history (T016).

Reads need viewer. Creating a verified healthy reference needs engineer and is audited; there is no
other way to create or change one.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.security import Principal, Role, require
from app.equipment.lifecycle import EquipmentStore
from app.equipment.maintenance import MaintenanceService
from app.monitoring.baselines.verified import BaselineService
from app.monitoring.degradation.history import degradation_history
from app.monitoring.features.store import FeatureStore
from app.monitoring.schemas import Baseline, BaselineVerification, DegradationHistory

router = APIRouter(tags=["baselines"])
DB = Annotated[Session, Depends(get_session)]
Viewer = Annotated[Principal, Depends(require(Role.VIEWER))]
Engineer = Annotated[Principal, Depends(require(Role.ENGINEER))]


@router.post("/baselines/verified", response_model=Baseline, status_code=201)
def verify_baseline(body: BaselineVerification, who: Engineer, db: DB) -> Baseline:
    EquipmentStore(db).component(body.component_id)
    out = BaselineService(db).verify(body, who)
    db.commit()
    return out


@router.get("/components/{component_id}/baselines", response_model=list[Baseline])
def list_baselines(component_id: str, _: Viewer, db: DB, include_superseded: bool = False) -> list[Baseline]:
    EquipmentStore(db).component(component_id)
    return BaselineService(db).baselines(component_id, include_superseded)


@router.get("/components/{component_id}/degradation", response_model=DegradationHistory)
def get_degradation(
    component_id: str,
    _: Viewer,
    db: DB,
    feature: Annotated[str, Query(min_length=1)],
    feature_ref: Annotated[str, Query(min_length=1)],
) -> DegradationHistory:
    EquipmentStore(db).component(component_id)
    vectors = FeatureStore(db).vectors(component_id, feature_ref)
    svc = BaselineService(db)
    refs = {}
    for lc in sorted({v.lifecycle_id for v in vectors}):
        ref = svc.verified(component_id, lc, feature_ref)
        if ref is not None:
            refs[lc] = ref
    events = MaintenanceService(db).events(component_id)
    return degradation_history(component_id, feature, vectors, refs, events)
