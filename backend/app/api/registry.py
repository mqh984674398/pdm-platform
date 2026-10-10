"""Champion/challenger registry (T026, UI-11): versions, candidates, promotion and rollback.

Reading needs viewer. Proposing, rejecting and rolling back need engineer; promoting needs admin.
Every change is audited by the registry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.core.registry import DeploymentRecord, DeploymentRegistry, DeploymentVersion, RegistryNotFoundError
from app.core.schemas import ContractModel
from app.core.security import Principal, Role, require
from app.decision.config import KIND
from app.optimization.deployment import ensure_champion, propose_from_run, propose_model
from app.optimization.service import latest
from app.optimization.suite import demo_suite
from app.prediction.models.registry import ModelRegistry

router = APIRouter(tags=["registry"])
DB = Annotated[Session, Depends(get_session)]
Viewer = Annotated[Principal, Depends(require(Role.VIEWER))]
Engineer = Annotated[Principal, Depends(require(Role.ENGINEER))]
DATA = Path(__file__).resolve().parents[3] / "Data"
BACKEND = Path(__file__).resolve().parents[2]


class Comment(ContractModel):
    comment: str = Field(min_length=1, max_length=2000)


class ConfigProposal(Comment):
    candidate_id: str


class ModelProposal(Comment):
    model_id: str


class Rollback(Comment):
    kind: str


class KindSummary(ContractModel):
    kind: str
    champion: DeploymentVersion | None
    candidates: int
    versions: int


def _models() -> ModelRegistry:
    d = Path(get_settings().models_dir)
    return ModelRegistry(d if d.is_absolute() else BACKEND / d)


def _kind_of(db: Session, version_id: str) -> str:
    row = db.get(DeploymentRecord, version_id)
    if row is None:
        raise RegistryNotFoundError(f"unknown version {version_id}")
    return row.kind


@router.get("/registry/kinds", response_model=list[KindSummary])
def kinds(_: Viewer, db: DB) -> list[KindSummary]:
    names = sorted(set(db.scalars(select(DeploymentRecord.kind))) | {KIND})
    out = []
    for k in names:
        hist = DeploymentRegistry(db, k).history()
        champ = next((v for v in hist if v.status == "CHAMPION"), None)
        out.append(
            KindSummary(
                kind=k,
                champion=champ,
                versions=len(hist),
                candidates=sum(v.status == "CANDIDATE" for v in hist),
            )
        )
    return out


@router.get("/registry/versions", response_model=list[DeploymentVersion])
def versions(kind: str, _: Viewer, db: DB) -> list[DeploymentVersion]:
    if kind == KIND:
        ensure_champion(db, True)
    return DeploymentRegistry(db, kind).history()


@router.get("/registry/models", response_model=list[str])
def trained_models(_: Viewer) -> list[str]:
    return [r.model_id for r in _models().records()]


@router.post("/registry/decision-config/candidates", response_model=DeploymentVersion)
def propose_config(body: ConfigProposal, who: Engineer, db: DB) -> DeploymentVersion:
    return propose_from_run(db, demo_suite(db, DATA), latest(), body.candidate_id, who, body.comment)


@router.post("/registry/models/candidates", response_model=DeploymentVersion)
def propose_trained_model(body: ModelProposal, who: Engineer, db: DB) -> DeploymentVersion:
    return propose_model(db, _models().get(body.model_id), who, body.comment)


@router.post("/registry/versions/{version_id}/promote", response_model=DeploymentVersion)
def promote(version_id: str, body: Comment, who: Engineer, db: DB) -> DeploymentVersion:
    return DeploymentRegistry(db, _kind_of(db, version_id)).promote(version_id, who, body.comment)


@router.post("/registry/versions/{version_id}/reject", response_model=DeploymentVersion)
def reject(version_id: str, body: Comment, who: Engineer, db: DB) -> DeploymentVersion:
    return DeploymentRegistry(db, _kind_of(db, version_id)).reject(version_id, who, body.comment)


@router.post("/registry/rollback", response_model=DeploymentVersion)
def rollback(body: Rollback, who: Engineer, db: DB) -> DeploymentVersion:
    return DeploymentRegistry(db, body.kind).rollback(who, body.comment)
