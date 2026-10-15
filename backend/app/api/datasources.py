"""Administrator management of TDengine data sources (D-044): create, edit, delete, test.

The account is write-only and never returned. Production sources need no approval (D-035)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.studio import _read_only
from app.api.visibility import Visible
from app.core.audit import record as audit
from app.core.db import get_session
from app.core.runmode import RunMode
from app.core.schemas import ContractModel
from app.core.security import Principal, Role, require
from app.datasource import managed as m
from app.datasource.query_service.defaults import ensure_standard_templates
from app.datasource.query_service.sources import DataSourceRegistry
from app.datasource.schemas import DataSourceKind
from app.datasource.sql import AdapterError
from app.datasource.tdengine import TdengineLayout
from app.signals.registry import SignalConfigStore

router = APIRouter(tags=["datasources"])
DB = Annotated[Session, Depends(get_session)]
Admin = Annotated[Principal, Depends(require(Role.ADMIN))]
ENV_PATH = Path(".env")  # backend\.env: the working directory of the service


class SourceConflictError(AdapterError):
    """The change would break something that uses the source, or touches a file-managed source."""


Hint = Literal["port_explorer", "not_rest", "unreachable", "auth", "database", "layout", "other"]


class TestCheck(ContractModel):
    key: Literal["credential", "reachable", "readOnly", "layout", "timeout", "rowLimit"]
    ok: bool
    detail: str | None = Field(default=None, description="The server's reason when the check failed")
    hint: Hint | None = Field(default=None, description="What the administrator should look at first")


class StructureColumn(ContractModel):
    name: str
    type: str
    is_tag: bool


class SourceStructure(ContractModel):
    stables: list[str]
    stable: str
    columns: list[StructureColumn]


def _hint(error: str, port: int | None, stage: str) -> Hint:
    low = error.lower()
    if stage == "layout":
        return "layout"
    if "not reachable" in low:
        return "port_explorer" if port == 6060 else "unreachable"
    if "returned http" in low:  # a web page, not taosAdapter's JSON: usually the wrong port
        return "port_explorer" if port == 6060 else "not_rest"
    if "auth" in low or "user" in low or "password" in low or "privilege" in low:
        return "auth"
    if "database" in low:
        return "database"
    return "other"


def _reg(request: Request) -> DataSourceRegistry:
    return request.app.state.sources


Reg = Annotated[DataSourceRegistry, Depends(_reg)]


def _view(reg: DataSourceRegistry, rec: m.ManagedSourceRecord | None, data_source_id: str) -> m.ManagedSource:
    loaded = {c.data_source_id for c in reg.configs()}
    if rec is None:
        c = reg.config(data_source_id)
        return m.ManagedSource(
            data_source_id=c.data_source_id, name=c.name, kind=c.kind, host=c.host, port=c.port,
            database=c.database, scheme=None, layout=None, managed=False,
            credential_set=bool(c.credential_ref), active=True, is_simulated=c.is_simulated,
        )  # fmt: skip
    cfg = rec.config
    import os

    return m.ManagedSource(
        data_source_id=rec.data_source_id, name=cfg["name"], kind=DataSourceKind.TDENGINE, host=cfg["host"],
        port=cfg["port"], database=cfg["database"], scheme=rec.scheme,
        layout=TdengineLayout.model_validate(rec.layout), managed=True,
        credential_set=bool(os.environ.get(m.secret_var(rec.data_source_id))),
        active=rec.data_source_id in loaded, is_simulated=False,
    )  # fmt: skip


@router.get("/admin/datasources", response_model=list[m.ManagedSource])
def list_sources(_: Admin, db: DB, reg: Reg, vis: Visible) -> list[m.ManagedSource]:
    recs = {r.data_source_id: r for r in db.query(m.ManagedSourceRecord)}
    out = [_view(reg, recs.get(c.data_source_id), c.data_source_id) for c in reg.configs()]
    out += [
        _view(reg, r, i)
        for i, r in sorted(recs.items())
        if i not in {c.data_source_id for c in reg.configs()}
    ]
    simulation = vis.mode == RunMode.SIMULATION
    out = [s for s in out if s.is_simulated == simulation]
    return sorted(out, key=lambda s: s.data_source_id)


@router.put("/admin/datasources/{data_source_id}", response_model=m.ManagedSource)
def put_source(
    data_source_id: str, body: m.ManagedSourceBody, who: Admin, db: DB, reg: Reg
) -> m.ManagedSource:
    if body.data_source_id != data_source_id:
        raise SourceConflictError("data_source_id in the body must match the URL")
    rec = db.get(m.ManagedSourceRecord, data_source_id)
    if rec is None and data_source_id in {c.data_source_id for c in reg.configs()}:
        raise SourceConflictError(f"'{data_source_id}' is defined in the datasources file")
    if (body.user is None) != (body.password is None):
        raise SourceConflictError("give the account user and password together")
    if body.user and body.password:
        m.write_secret(ENV_PATH, data_source_id, body.user, body.password)
    layout = m.layout_of(body)  # a changed layout needs a new test before it counts as verified
    fields = dict(
        config=m.config_of(body).model_dump(mode="json"), layout=layout.model_dump(mode="json"),
        scheme=body.scheme, updated_by=who.user_id, updated_at=m.stamp(),
    )  # fmt: skip
    if rec is None:
        rec = m.ManagedSourceRecord(data_source_id=data_source_id, **fields)
        db.add(rec)
    else:
        for k, v in fields.items():
            setattr(rec, k, v)
    audit(db, who, "datasource.save", "datasource", data_source_id, host=body.host, database=body.database,
          stable=body.stable, account_changed=bool(body.user))  # fmt: skip
    db.flush()
    reg.remove(data_source_id)
    try:
        reg.add(*m.build(rec))
    except AdapterError:
        pass  # no account yet: stays inactive until one is set
    db.commit()
    return _view(reg, rec, data_source_id)


@router.delete("/admin/datasources/{data_source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(data_source_id: str, who: Admin, db: DB, reg: Reg) -> Response:
    rec = db.get(m.ManagedSourceRecord, data_source_id)
    if rec is None:
        raise SourceConflictError(f"'{data_source_id}' is not a source managed here")
    used = {x.data_source_id for x in SignalConfigStore(db).current().content.mappings}
    if data_source_id in used:
        raise SourceConflictError(f"'{data_source_id}' is used by signal mappings")
    db.delete(rec)
    audit(db, who, "datasource.delete", "datasource", data_source_id)
    reg.remove(data_source_id)
    m.remove_secret(ENV_PATH, data_source_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/admin/datasources/{data_source_id}/test", response_model=list[TestCheck])
def test_source(data_source_id: str, who: Admin, db: DB, reg: Reg) -> list[TestCheck]:
    rec = db.get(m.ManagedSourceRecord, data_source_id)
    if rec is None:
        raise SourceConflictError(f"'{data_source_id}' is not a source managed here")
    try:
        config, adapter = m.build(rec)
    except AdapterError:
        return [TestCheck(key="credential", ok=False)]
    reachable = read_only = layout_ok = False
    problem: dict[str, tuple[str, Hint]] = {}  # check key -> (reason, hint)
    port = config.port
    try:
        adapter.sql("SELECT SERVER_VERSION()")
        reachable = True
    except (AdapterError, SQLAlchemyError, OSError) as exc:
        problem["reachable"] = (str(exc), _hint(str(exc), port, "reachable"))
    if reachable:
        try:
            read_only = config.read_only and _read_only(adapter)
            if not read_only:
                problem["readOnly"] = ("the account can write or could not be verified read-only", "auth")
        except (AdapterError, SQLAlchemyError, OSError, KeyError, ValueError, IndexError) as exc:
            problem["readOnly"] = (f"could not check the account's privileges: {exc}", "auth")
        try:
            adapter.check_layout()
            layout_ok = True
        except (AdapterError, SQLAlchemyError, OSError) as exc:
            problem["layout"] = (str(exc), _hint(str(exc), port, "layout"))
    if layout_ok:  # the layout was checked against the real database
        # the settled layout (real column names, expanded value_* patterns) is what gets stored
        rec.layout = {**adapter.layout.model_dump(mode="json"), "verified": True}
        reg.remove(data_source_id)
        reg.add(*m.build(rec))
        db.flush()
        # a source added here after start-up has no query templates until one exists for it
        ensure_standard_templates(db, reg)
    audit(db, who, "datasource.test", "datasource", data_source_id, reachable=reachable,
          read_only=read_only, layout=layout_ok)  # fmt: skip
    db.commit()

    def check(key: str, ok: bool) -> TestCheck:
        why = problem.get(key)
        return TestCheck(key=key, ok=ok, detail=why[0] if why and not ok else None,
                         hint=why[1] if why and not ok else None)  # fmt: skip

    return [
        check("credential", True),
        check("reachable", reachable),
        check("readOnly", read_only),
        check("layout", layout_ok),
        check("timeout", config.statement_timeout_s <= 300),
        check("rowLimit", config.max_rows <= 2_000_000),
    ]


@router.get("/admin/datasources/{data_source_id}/structure", response_model=SourceStructure)
def source_structure(data_source_id: str, _: Admin, db: DB, stable: str | None = None) -> SourceStructure:
    """Super tables of the database and the columns/tags of one of them, read with the saved account,
    so the layout fields can be picked from what the database really has."""
    rec = db.get(m.ManagedSourceRecord, data_source_id)
    if rec is None:
        raise SourceConflictError(f"'{data_source_id}' is not a source managed here")
    _, adapter = m.build(rec)
    stables, cols = adapter.structure(stable)
    return SourceStructure(
        stables=stables,
        stable=stable or rec.layout["stable"],
        columns=[StructureColumn(name=n, type=t, is_tag=tag) for n, t, tag in cols],
    )
