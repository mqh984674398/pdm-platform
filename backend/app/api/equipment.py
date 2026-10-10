"""Topology, lifecycles, maintenance events and workflows (T014).

Reads need viewer. Topology, installation and usage need engineer; recording maintenance and moving a
workflow forward need maintenance; closing a review needs engineer (checked in the service). Every
change is audited in the same transaction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.security import Principal, Role, require
from app.equipment.lifecycle import EquipmentConflictError, EquipmentStore
from app.equipment.maintenance import MaintenanceService
from app.equipment.schemas import (
    ComponentAging,
    ComponentInstance,
    ComponentLifecycle,
    LifecycleInstall,
    Machine,
    MaintenanceEvent,
    MaintenanceEventCreate,
    MaintenanceRecordResult,
    MaintenanceWorkflow,
    UsageRecord,
    WorkflowTransitionRequest,
)

router = APIRouter(tags=["equipment"])
DB = Annotated[Session, Depends(get_session)]
Viewer = Annotated[Principal, Depends(require(Role.VIEWER))]
Maintainer = Annotated[Principal, Depends(require(Role.MAINTENANCE))]
Engineer = Annotated[Principal, Depends(require(Role.ENGINEER))]


def _same(path_id: str, body_id: str, field: str) -> None:
    if path_id != body_id:
        raise EquipmentConflictError(f"{field} in the body must match the URL")


@router.get("/machines", response_model=list[Machine])
def list_machines(_: Viewer, db: DB) -> list[Machine]:
    return EquipmentStore(db).machines()


@router.put("/machines/{machine_id}", response_model=Machine)
def put_machine(machine_id: str, body: Machine, who: Engineer, db: DB) -> Machine:
    _same(machine_id, body.machine_id, "machine_id")
    out = EquipmentStore(db).put_machine(body, who)
    db.commit()
    return out


@router.get("/machines/{machine_id}/components", response_model=list[ComponentInstance])
def list_components(machine_id: str, _: Viewer, db: DB) -> list[ComponentInstance]:
    store = EquipmentStore(db)
    store.machine(machine_id)
    return store.components(machine_id)


@router.get("/components/{component_id}", response_model=ComponentInstance)
def get_component(component_id: str, _: Viewer, db: DB) -> ComponentInstance:
    return EquipmentStore(db).component(component_id)


@router.put("/components/{component_id}", response_model=ComponentInstance)
def put_component(component_id: str, body: ComponentInstance, who: Engineer, db: DB) -> ComponentInstance:
    _same(component_id, body.component_id, "component_id")
    out = EquipmentStore(db).put_component(body, who)
    db.commit()
    return out


@router.get("/components/{component_id}/lifecycles", response_model=list[ComponentLifecycle])
def list_lifecycles(component_id: str, _: Viewer, db: DB) -> list[ComponentLifecycle]:
    return EquipmentStore(db).lifecycles(component_id)


@router.post("/components/{component_id}/lifecycles", response_model=ComponentLifecycle, status_code=201)
def install(component_id: str, body: LifecycleInstall, who: Engineer, db: DB) -> ComponentLifecycle:
    out = EquipmentStore(db).install(component_id, body.installed_at, who, body.comment)
    db.commit()
    return out


@router.post("/lifecycles/{lifecycle_id}/usage", response_model=ComponentLifecycle)
def record_usage(lifecycle_id: str, body: UsageRecord, who: Engineer, db: DB) -> ComponentLifecycle:
    out = EquipmentStore(db).record_usage(lifecycle_id, body, who)
    db.commit()
    return out


@router.get("/components/{component_id}/aging", response_model=ComponentAging)
def aging(component_id: str, _: Viewer, db: DB, at: datetime | None = None) -> ComponentAging:
    when = at or datetime.now(UTC)
    lc = EquipmentStore(db).lifecycle_at(component_id, when)
    times = [
        e.performed_at
        for e in MaintenanceService(db).events(component_id)
        if e.lifecycle_id == lc.lifecycle_id
    ]
    return EquipmentStore(db).aging(component_id, when, times)


@router.get("/components/{component_id}/maintenance-events", response_model=list[MaintenanceEvent])
def list_events(component_id: str, _: Viewer, db: DB) -> list[MaintenanceEvent]:
    return MaintenanceService(db).events(component_id)


@router.post("/maintenance-events", response_model=MaintenanceRecordResult, status_code=201)
def record_event(body: MaintenanceEventCreate, who: Maintainer, db: DB) -> MaintenanceRecordResult:
    out = MaintenanceService(db).record_event(body, who)
    db.commit()
    return out


@router.get("/maintenance-workflows", response_model=list[MaintenanceWorkflow])
def list_workflows(
    _: Viewer,
    db: DB,
    component_id: str | None = None,
    open_only: Annotated[bool, Query(alias="open")] = False,
) -> list[MaintenanceWorkflow]:
    return MaintenanceService(db).workflows(component_id, open_only)


@router.get("/maintenance-workflows/{workflow_id}", response_model=MaintenanceWorkflow)
def get_workflow(workflow_id: str, _: Viewer, db: DB) -> MaintenanceWorkflow:
    return MaintenanceService(db).workflow(workflow_id)


@router.post("/maintenance-workflows/{workflow_id}/transitions", response_model=MaintenanceWorkflow)
def transition(
    workflow_id: str, body: WorkflowTransitionRequest, who: Maintainer, db: DB
) -> MaintenanceWorkflow:
    out = MaintenanceService(db).transition(workflow_id, body, who)
    db.commit()
    return out
