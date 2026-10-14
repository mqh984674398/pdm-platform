# ruff: noqa: E501
"""Prediction configuration versions: draft, validate, publish, activate (D-044). Writes need an administrator."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.schemas import ContractModel
from app.core.security import Principal, Role, require
from app.datasource.query_service.sources import DataSourceRegistry
from app.decision import config_validation as cv
from app.decision import pipeline_config as pc

router = APIRouter(tags=["prediction-config"])
DB = Annotated[Session, Depends(get_session)]
Viewer = Annotated[Principal, Depends(require(Role.VIEWER))]
Admin = Annotated[Principal, Depends(require(Role.ADMIN))]


def _sources(request: Request) -> DataSourceRegistry:
    return request.app.state.sources


Sources = Annotated[DataSourceRegistry, Depends(_sources)]


class DraftBody(ContractModel):
    content: pc.ConfigContent | None = None
    copy_from_component: str | None = None  # copy the active configuration of another component


class PublishBody(ContractModel):
    comment: str


@router.get("/algorithm-catalog", response_model=list[pc.AlgorithmSpec])
def catalog(_: Viewer) -> list[pc.AlgorithmSpec]:
    return list(pc.CATALOG.values())


@router.get("/components/{component_id}/prediction-configs", response_model=list[pc.PredictionConfig])
def versions(component_id: str, _: Viewer, db: DB) -> list[pc.PredictionConfig]:
    return pc.PredictionConfigStore(db).versions(component_id)


@router.post("/components/{component_id}/prediction-configs", response_model=pc.PredictionConfig)
def create(component_id: str, body: DraftBody, who: Admin, db: DB) -> pc.PredictionConfig:
    store = pc.PredictionConfigStore(db)
    content = body.content
    if body.copy_from_component:
        src = store.active(body.copy_from_component)
        if src is None:
            raise pc.PredictionConfigError("the component to copy from has no active configuration")
        other = next(c for c in _components(db) if c.component_id == body.copy_from_component)
        mine = next((c for c in _components(db) if c.component_id == component_id), None)
        if mine is None or mine.type != other.type:
            raise pc.PredictionConfigError(
                "a configuration can be copied only between components of the same type"
            )
        content = src.content.model_copy(update={"template_from": body.copy_from_component})
    out = store.create_draft(component_id, content or pc.ConfigContent(), who)
    db.commit()
    return out


def _components(db: Session):
    from app.equipment.lifecycle import EquipmentStore

    return EquipmentStore(db).components()


@router.get("/prediction-configs/{config_id}", response_model=pc.PredictionConfig)
def get(config_id: str, _: Viewer, db: DB) -> pc.PredictionConfig:
    return pc.PredictionConfigStore(db).get(config_id)


@router.put("/prediction-configs/{config_id}", response_model=pc.PredictionConfig)
def update(config_id: str, body: pc.ConfigContent, who: Admin, db: DB) -> pc.PredictionConfig:
    out = pc.PredictionConfigStore(db).update_draft(config_id, body, who)
    db.commit()
    return out


@router.delete("/prediction-configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(config_id: str, who: Admin, db: DB) -> Response:
    pc.PredictionConfigStore(db).delete_draft(config_id, who)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/prediction-configs/{config_id}/clone", response_model=pc.PredictionConfig)
def clone(config_id: str, who: Admin, db: DB) -> pc.PredictionConfig:
    out = pc.PredictionConfigStore(db).clone(config_id, who)
    db.commit()
    return out


@router.post("/components/{component_id}/prediction-configs/compile", response_model=pc.CompileResult)
def compile_(component_id: str, body: pc.ConfigContent, _: Admin, db: DB) -> pc.CompileResult:
    return pc.compile_config(db, component_id, body)[0]


@router.post("/prediction-configs/{config_id}/validate", response_model=pc.PredictionConfig)
def validate(config_id: str, who: Admin, db: DB, sources: Sources) -> pc.PredictionConfig:
    store = pc.PredictionConfigStore(db)
    cfg = store.get(config_id)
    out = store.save_validation(config_id, cv.run_all(db, sources, cfg), who)
    db.commit()
    return out


@router.post("/prediction-configs/{config_id}/publish", response_model=pc.PredictionConfig)
def publish(config_id: str, body: PublishBody, who: Admin, db: DB) -> pc.PredictionConfig:
    out = pc.PredictionConfigStore(db).publish(config_id, who, body.comment)
    db.commit()
    return out


@router.post("/prediction-configs/{config_id}/activate", response_model=pc.PredictionConfig)
def activate(config_id: str, who: Admin, db: DB) -> pc.PredictionConfig:
    out = pc.PredictionConfigStore(db).activate(config_id, who)
    db.commit()
    return out


@router.post(
    "/components/{component_id}/prediction-configs/deactivate", status_code=status.HTTP_204_NO_CONTENT
)
def deactivate(component_id: str, who: Admin, db: DB) -> Response:
    pc.PredictionConfigStore(db).deactivate(component_id, who)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
