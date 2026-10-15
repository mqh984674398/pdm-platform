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
from app.decision import plugins
from app.prediction.models import deep

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


class DeepAdapterInfo(ContractModel):
    family: str
    contract: deep.InputContract
    available: bool
    unavailable_reason: str | None


@router.get("/deep-model-adapters", response_model=list[DeepAdapterInfo])
def deep_adapters(_: Viewer) -> list[DeepAdapterInfo]:
    status = deep.adapter_status()
    return [
        DeepAdapterInfo(
            family=f, contract=a.contract, available=status[f] is None, unavailable_reason=status[f]
        )
        for f, a in sorted(deep.ADAPTERS.items())
    ]


class AlgorithmUse(ContractModel):
    component_id: str
    config_id: str
    version: int
    stage_id: str
    enabled: bool


class AlgorithmEntry(ContractModel):
    spec: pc.AlgorithmSpec
    adapter_available: bool | None = None  # deep-model algorithms only
    adapter_reason: str | None = None
    active_uses: list[AlgorithmUse]  # stages of the active configurations that run this algorithm
    draft_uses: int  # stages in unpublished drafts


class AlgorithmModels(ContractModel):
    algorithms: list[AlgorithmEntry]
    deep_adapters: list[DeepAdapterInfo]
    plugins: list[plugins.PluginSpec]


@router.get("/algorithm-models", response_model=AlgorithmModels)
def algorithm_models(_: Viewer, db: DB) -> AlgorithmModels:
    """The algorithm library and where each algorithm is used (read-only; selection happens in a component's
    configuration)."""
    store = pc.PredictionConfigStore(db)
    uses: dict[str, list[AlgorithmUse]] = {}
    drafts: dict[str, int] = {}
    for comp in _components(db):
        for cfg in store.versions(comp.component_id):
            for st in cfg.content.pipeline:
                if cfg.active:
                    uses.setdefault(st.algorithm, []).append(
                        AlgorithmUse(
                            component_id=comp.component_id, config_id=cfg.config_id,
                            version=cfg.version, stage_id=st.stage_id, enabled=st.enabled,
                        )
                    )  # fmt: skip
                elif cfg.status != pc.ConfigStatus.PUBLISHED:
                    drafts[st.algorithm] = drafts.get(st.algorithm, 0) + 1
    adapters = deep_adapters(_)
    by_family = {a.family: a for a in adapters}
    entries = []
    for spec in pc.CATALOG.values():
        ad = by_family.get(spec.deep_family or "")
        entries.append(
            AlgorithmEntry(
                spec=spec,
                adapter_available=ad.available if ad else None,
                adapter_reason=ad.unavailable_reason if ad else None,
                active_uses=uses.get(spec.algorithm_id, []),
                draft_uses=drafts.get(spec.algorithm_id, 0),
            )
        )
    return AlgorithmModels(algorithms=entries, deep_adapters=adapters, plugins=plugins.plugin_specs())


@router.get("/components/{component_id}/recommended-config", response_model=pc.Recommendation)
def recommended(component_id: str, _: Viewer, db: DB) -> pc.Recommendation:
    return pc.recommend_config(db, component_id)


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
    result = pc.compile_config(db, component_id, body)[0]
    return result.model_copy(update={"issues": [*result.issues, *cv.runtime_issues(db, component_id)]})


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
