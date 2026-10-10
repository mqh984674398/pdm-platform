"""Rules and alarms (T017).

Reads need viewer. Disabling or enabling a statistical rule needs engineer, a safety rule admin
(checked in the service). Running the rules on stored features needs engineer. Acknowledging and
resolving alarms need maintenance. Every change is audited. Alarms send no notifications.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.security import Principal, Role, require
from app.decision.fleet import FleetHealthService
from app.equipment.lifecycle import EquipmentStore
from app.monitoring.alarms.service import AlarmService
from app.monitoring.baselines.verified import BaselineService
from app.monitoring.features.store import FeatureStore
from app.monitoring.rules.engine import evaluate
from app.monitoring.rules.settings import RuleSettings
from app.monitoring.schemas import (
    Alarm,
    AlarmAction,
    AlarmEvaluationRequest,
    AlarmEvaluationResult,
    AlarmStatus,
    RuleChange,
    RuleSetStatus,
)

router = APIRouter(tags=["alarms"])
DB = Annotated[Session, Depends(get_session)]
Viewer = Annotated[Principal, Depends(require(Role.VIEWER))]
Maintainer = Annotated[Principal, Depends(require(Role.MAINTENANCE))]
Engineer = Annotated[Principal, Depends(require(Role.ENGINEER))]


@router.get("/rules", response_model=RuleSetStatus)
def get_rules(_: Viewer, db: DB) -> RuleSetStatus:
    return RuleSettings(db).status()


@router.put("/rules/{rule_id}", response_model=RuleSetStatus)
def change_rule(rule_id: str, body: RuleChange, who: Engineer, db: DB) -> RuleSetStatus:
    out = RuleSettings(db).change(rule_id, body, who)
    db.commit()
    return out


@router.post("/alarms/evaluate", response_model=AlarmEvaluationResult)
def evaluate_alarms(body: AlarmEvaluationRequest, who: Engineer, db: DB) -> AlarmEvaluationResult:
    EquipmentStore(db).component(body.component_id)
    vectors = FeatureStore(db).vectors(body.component_id, body.feature_ref)
    baselines = BaselineService(db)
    refs = {}
    for lc in sorted({v.lifecycle_id for v in vectors}):
        ref = baselines.verified(body.component_id, lc, body.feature_ref)
        if ref is not None:
            refs[lc] = ref
    settings = RuleSettings(db)
    svc = FleetHealthService(db)  # rule set in force: registry champion or the default
    evals = evaluate(vectors, refs, svc.config.rules, settings.disabled(), rules_version=svc.rules_version())
    raised, updated = AlarmService(db).sync(evals, who)
    db.commit()
    return AlarmEvaluationResult(
        evaluations=evals, raised=raised, updated=updated, is_simulated=any(v.is_simulated for v in vectors)
    )


@router.get("/alarms", response_model=list[Alarm])
def list_alarms(
    _: Viewer, db: DB, component_id: str | None = None, status: AlarmStatus | None = None
) -> list[Alarm]:
    return AlarmService(db).alarms(component_id, status)


@router.post("/alarms/{alarm_id}/acknowledge", response_model=Alarm)
def acknowledge_alarm(alarm_id: str, body: AlarmAction, who: Maintainer, db: DB) -> Alarm:
    out = AlarmService(db).acknowledge(alarm_id, who, body.comment)
    db.commit()
    return out


@router.post("/alarms/{alarm_id}/resolve", response_model=Alarm)
def resolve_alarm(alarm_id: str, body: AlarmAction, who: Maintainer, db: DB) -> Alarm:
    out = AlarmService(db).resolve(alarm_id, who, body.comment)
    db.commit()
    return out
