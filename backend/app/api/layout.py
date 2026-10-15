"""Equipment overview layout (D-054): machine order and background pictures."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.visibility import Visible
from app.core.db import get_session
from app.core.security import Principal, Role, require
from app.equipment.layout import BackgroundChange, LayoutStore, MachineLayout, OrderChange

router = APIRouter(tags=["plant"])
DB = Annotated[Session, Depends(get_session)]
Viewer = Annotated[Principal, Depends(require(Role.VIEWER))]
Admin = Annotated[Principal, Depends(require(Role.ADMIN))]


@router.get("/machine-layout", response_model=list[MachineLayout])
def read_layout(_: Viewer, db: DB, vis: Visible) -> list[MachineLayout]:
    keep = vis.machine_ids()
    return [m for m in LayoutStore(db).all() if m.machine_id in keep]


@router.put("/machine-layout/order", status_code=status.HTTP_204_NO_CONTENT)
def put_order(body: OrderChange, who: Admin, db: DB) -> Response:
    LayoutStore(db).set_order(body, who)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/machine-layout/{machine_id}/background", status_code=status.HTTP_204_NO_CONTENT)
def put_background(machine_id: str, body: BackgroundChange, who: Admin, db: DB) -> Response:
    LayoutStore(db).set_background(machine_id, body, who)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
