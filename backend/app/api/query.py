"""Data source and query template endpoints (T010)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.visibility import Visible, source_in_mode
from app.core import audit
from app.core.db import get_session
from app.core.security import Principal, Role, require
from app.datasource.query_service.registry import TemplateConflictError, TemplateRegistry
from app.datasource.query_service.service import QueryService, allowed_tables
from app.datasource.query_service.sources import DataSourceRegistry
from app.datasource.schemas import (
    DataSourceConfig,
    QueryResult,
    QueryRunRequest,
    QueryTemplate,
    QueryTemplateAdminView,
    QueryTemplateSpec,
    SourceMetadata,
    SourceSchema,
)

router = APIRouter(tags=["datasources"])
DB = Annotated[Session, Depends(get_session)]
Viewer = Annotated[Principal, Depends(require(Role.VIEWER))]
Engineer = Annotated[Principal, Depends(require(Role.ENGINEER))]
Admin = Annotated[Principal, Depends(require(Role.ADMIN))]


def sources(request: Request) -> DataSourceRegistry:
    return request.app.state.sources


def service(request: Request) -> QueryService:
    return request.app.state.query_service


Sources = Annotated[DataSourceRegistry, Depends(sources)]
Service = Annotated[QueryService, Depends(service)]


@router.get("/datasources", response_model=list[DataSourceConfig])
def list_sources(who: Viewer, reg: Sources, vis: Visible) -> list[DataSourceConfig]:
    return [c for c in reg.configs_for(who) if source_in_mode(c, vis.mode)]


@router.get("/datasources/{data_source_id}/metadata", response_model=SourceMetadata)
def source_metadata(data_source_id: str, who: Viewer, reg: Sources) -> SourceMetadata:
    reg.require_access(data_source_id, who)
    return reg.adapter(data_source_id).discover()


@router.get("/datasources/{data_source_id}/schema", response_model=SourceSchema)
def source_schema(data_source_id: str, who: Engineer, reg: Sources) -> SourceSchema:
    reg.require_access(data_source_id, who)
    return reg.adapter(data_source_id).inspect_schema()


@router.get("/query-templates", response_model=list[QueryTemplate])
def list_templates(who: Viewer, db: DB, reg: Sources) -> list[QueryTemplate]:
    usable = {c.data_source_id for c in reg.configs_for(who)}
    return [r.to_template() for r in TemplateRegistry(db).list_active() if r.data_source_id in usable]


@router.post("/query-templates/{template_id}/run", response_model=QueryResult)
def run_template(
    template_id: str, body: QueryRunRequest, who: Viewer, db: DB, svc: Service, reg: Sources
) -> QueryResult:
    template = TemplateRegistry(db).active(template_id)
    reg.require_access(template.data_source_id, who)
    return svc.run(template, body)


@router.get("/admin/query-templates", response_model=list[QueryTemplateAdminView])
def admin_list_templates(_: Admin, db: DB) -> list[QueryTemplateAdminView]:
    return [r.to_admin_view() for r in TemplateRegistry(db).list_active()]


@router.get("/admin/query-templates/{template_id}/history", response_model=list[QueryTemplateAdminView])
def admin_template_history(template_id: str, _: Admin, db: DB) -> list[QueryTemplateAdminView]:
    return [r.to_admin_view() for r in TemplateRegistry(db).history(template_id)]


@router.post(
    "/admin/query-templates", response_model=QueryTemplateAdminView, status_code=status.HTTP_201_CREATED
)
def admin_create_template(
    spec: QueryTemplateSpec, who: Admin, db: DB, reg: Sources
) -> QueryTemplateAdminView:
    tables = allowed_tables(reg.adapter(spec.data_source_id))
    rec = TemplateRegistry(db).create(spec, who, tables)
    db.commit()
    return rec.to_admin_view()


@router.put("/admin/query-templates/{template_id}", response_model=QueryTemplateAdminView)
def admin_update_template(
    template_id: str, spec: QueryTemplateSpec, who: Admin, db: DB, reg: Sources
) -> QueryTemplateAdminView:
    if spec.template_id != template_id:
        raise TemplateConflictError("template_id in the body must match the URL")
    tables = allowed_tables(reg.adapter(spec.data_source_id))
    rec = TemplateRegistry(db).update(spec, who, tables)
    db.commit()
    return rec.to_admin_view()


@router.delete("/admin/query-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_retire_template(template_id: str, who: Admin, db: DB) -> Response:
    TemplateRegistry(db).retire(template_id, who)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/audit", response_model=list[audit.AuditEntry])
def admin_audit(_: Admin, db: DB, object_type: str | None = None, object_id: str | None = None):
    return audit.entries(db, object_type, object_id)
