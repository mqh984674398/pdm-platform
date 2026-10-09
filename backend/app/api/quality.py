"""Data quality and alignment report endpoint (T012)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.security import Principal, Role, require
from app.datasource.query_service.sources import DataSourceRegistry
from app.monitoring.quality.service import quality_report
from app.monitoring.schemas import QualityRequest, QualityResponse
from app.signals.registry import SignalConfigStore

router = APIRouter(tags=["quality"])


def _sources(request: Request) -> DataSourceRegistry:
    return request.app.state.sources


@router.post("/quality/report", response_model=QualityResponse)
def report(
    body: QualityRequest,
    _: Annotated[Principal, Depends(require(Role.VIEWER))],
    db: Annotated[Session, Depends(get_session)],
    reg: Annotated[DataSourceRegistry, Depends(_sources)],
) -> QualityResponse:
    return quality_report(reg, SignalConfigStore(db).current().content, body)
