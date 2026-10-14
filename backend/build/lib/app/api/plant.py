"""Plant structure endpoints (D-037): workshop → process → machine, and machine components (D-038).

Everyone signed in can read the tree; every change needs an administrator and is audited.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.security import Principal, Role, require
from app.equipment.lifecycle import EquipmentConflictError
from app.equipment.plant import (
    ComponentChange,
    MachineCreate,
    MachinePlacement,
    PlantNodeChange,
    PlantStore,
    PlantTree,
    machine_model,
)
from app.equipment.schemas import ComponentInstance, Machine

router = APIRouter(tags=["plant"])
DB = Annotated[Session, Depends(get_session)]
Viewer = Annotated[Principal, Depends(require(Role.VIEWER))]
Admin = Annotated[Principal, Depends(require(Role.ADMIN))]


@router.get("/plant-tree", response_model=PlantTree)
def plant_tree(_: Viewer, db: DB) -> PlantTree:
    return PlantStore(db).tree()


@router.put("/plant-nodes/{node_id}", response_model=PlantTree)
def put_node(node_id: str, body: PlantNodeChange, who: Admin, db: DB) -> PlantTree:
    if body.node_id != node_id:
        raise EquipmentConflictError("node_id in the body must match the URL")
    store = PlantStore(db)
    store.put_node(body, who)
    db.commit()
    return store.tree()


@router.delete("/plant-nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_node(node_id: str, who: Admin, db: DB) -> Response:
    PlantStore(db).delete_node(node_id, who)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/plant-machines", response_model=Machine, status_code=status.HTTP_201_CREATED)
def create_machine(body: MachineCreate, who: Admin, db: DB) -> Machine:
    rec = PlantStore(db).create_machine(body, who)
    db.commit()
    return machine_model(db, rec)


@router.put("/plant-machines/{machine_id}", response_model=Machine)
def place_machine(machine_id: str, body: MachinePlacement, who: Admin, db: DB) -> Machine:
    rec = PlantStore(db).place_machine(machine_id, body, who)
    db.commit()
    return machine_model(db, rec)


@router.delete("/plant-machines/{machine_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_machine(machine_id: str, who: Admin, db: DB) -> Response:
    PlantStore(db).delete_machine(machine_id, who)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/plant-machines/{machine_id}/components/{component_id}", response_model=ComponentInstance)
def put_component(
    machine_id: str, component_id: str, body: ComponentChange, who: Admin, db: DB
) -> ComponentInstance:
    if body.component_id != component_id:
        raise EquipmentConflictError("component_id in the body must match the URL")
    out = PlantStore(db).put_component(machine_id, body, who)
    db.commit()
    return out


@router.delete("/plant-components/{component_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_component(component_id: str, who: Admin, db: DB) -> Response:
    PlantStore(db).delete_component(component_id, who)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
