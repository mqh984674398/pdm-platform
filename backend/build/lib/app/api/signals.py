"""Signal configuration and preview endpoints (T011).

Reads need viewer; changes need engineer. Every change returns the new configuration version.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime, BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.modules import require_module
from app.core.schemas import TimeWindow
from app.core.security import Principal, Role, require
from app.datasource.query_service.sources import DataSourceRegistry
from app.signals.preview import UnknownSignalError, preview
from app.signals.registry import ConfigConflictError, SignalConfigStore
from app.signals.schemas import (
    DeviceConfigChange,
    PreviewRequest,
    PreviewResponse,
    SignalConfigState,
    SignalConfigVersion,
    SignalConfigVersionDetail,
    SignalDefinitionChange,
    SignalGroupChange,
    SignalMappingChange,
    VisualizationTemplateChange,
)

router = APIRouter(tags=["signals"])
DB = Annotated[Session, Depends(get_session)]
Viewer = Annotated[Principal, Depends(require(Role.VIEWER))]
Engineer = Annotated[Principal, Depends(require(Role.ENGINEER))]


def _sources(request: Request) -> DataSourceRegistry:
    return request.app.state.sources


Sources = Annotated[DataSourceRegistry, Depends(_sources)]


@router.get("/signal-config", response_model=SignalConfigState)
def current_config(_: Viewer, db: DB) -> SignalConfigState:
    return SignalConfigStore(db).current()


@router.get("/signal-config/versions", response_model=list[SignalConfigVersion])
def config_versions(_: Viewer, db: DB) -> list[SignalConfigVersion]:
    return SignalConfigStore(db).versions()


@router.get("/signal-config/versions/{version}", response_model=SignalConfigVersionDetail)
def config_version(version: int, _: Viewer, db: DB) -> SignalConfigVersionDetail:
    return SignalConfigStore(db).get(version)


@router.put(
    "/signal-config/sources/{data_source_id}/devices/{device_id}",
    response_model=SignalConfigVersion,
    dependencies=[require_module("signals")],
)
def replace_device(
    data_source_id: str, device_id: str, body: DeviceConfigChange, who: Engineer, db: DB, reg: Sources
) -> SignalConfigVersion:
    reg.config(data_source_id)  # 404 for unknown sources
    version = SignalConfigStore(db).replace_device(data_source_id, device_id, body, who)
    db.commit()
    return version


def _item_routes(collection: str, path: str, change_model: type[BaseModel], id_field: str) -> None:
    """PUT (create or replace) and DELETE for one collection; both write a new version."""

    def put(item_id: str, body: BaseModel, who: Engineer, db: DB) -> SignalConfigVersion:
        if getattr(body.item, id_field) != item_id:  # type: ignore[attr-defined]
            raise ConfigConflictError(f"{id_field} in the body must match the URL")
        version = SignalConfigStore(db).put_item(collection, body.item, who, body.comment, body.base_version)  # type: ignore[attr-defined]
        db.commit()
        return version

    def delete(
        item_id: str,
        who: Engineer,
        db: DB,
        comment: Annotated[str, Query(max_length=500)] = "",
        base_version: Annotated[int | None, Query(ge=0)] = None,
    ) -> SignalConfigVersion:
        version = SignalConfigStore(db).delete_item(collection, item_id, who, comment, base_version)
        db.commit()
        return version

    put.__annotations__["body"] = change_model  # concrete body type per collection for OpenAPI
    put.__name__, delete.__name__ = f"put_{collection}", f"delete_{collection}"
    gate = [require_module("signals")]
    router.put(f"/signal-config/{path}/{{item_id}}", response_model=SignalConfigVersion, dependencies=gate)(
        put
    )
    router.delete(
        f"/signal-config/{path}/{{item_id}}", response_model=SignalConfigVersion, dependencies=gate
    )(delete)


_item_routes("signals", "signals", SignalDefinitionChange, "signal_id")
_item_routes("mappings", "mappings", SignalMappingChange, "signal_id")
_item_routes("groups", "groups", SignalGroupChange, "group_id")
_item_routes("visualizations", "visualizations", VisualizationTemplateChange, "template_id")


@router.post(
    "/signals/preview", response_model=PreviewResponse, dependencies=[require_module("signals")]
)
def preview_signals(body: PreviewRequest, _: Viewer, db: DB, reg: Sources) -> PreviewResponse:
    return preview(reg, SignalConfigStore(db).current().content, body)


@router.get(
    "/signals/{signal_id}/preview",
    response_model=PreviewResponse,
    dependencies=[require_module("signals")],
)
def preview_saved_signal(
    signal_id: str,
    start: AwareDatetime,
    end: AwareDatetime,
    _: Viewer,
    db: DB,
    reg: Sources,
    max_points: Annotated[int, Query(ge=10, le=10_000)] = 1000,
    include_normalized: bool = True,
) -> PreviewResponse:
    content = SignalConfigStore(db).current().content
    mapping = next((m for m in content.mappings if m.signal_id == signal_id), None)
    if mapping is None:
        raise UnknownSignalError(f"signal '{signal_id}' has no saved mapping")
    req = PreviewRequest(
        mappings=[mapping],
        window=TimeWindow(start=start, end=end),
        max_points=max_points,
        include_normalized=include_normalized,
    )
    return preview(reg, content, req)
