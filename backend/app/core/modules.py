"""Which screens (modules) each role may use (SEC-01, D-033).

Administrators configure, per role, which of the twelve modules are visible; the browser hides the rest
and the API refuses module-owned endpoints for roles that do not have the module. Roles without a saved
row see every module, which is how the platform behaved before this setting existed. The administrator
role always has every module and cannot be restricted, so nobody can lock the platform out of its own
configuration.

Monitoring reads shared by several screens (fleet, machines, components, time series, baselines, the
current signal configuration, alarm lists) stay governed by role only; ``require_module`` guards the
endpoints that belong to a module's own work, such as Studio, optimization, model registry and the
assistant, and the actions taken on alarms and maintenance workflows.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from pydantic import Field
from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.audit import record as audit
from app.core.db import Base, get_session
from app.core.schemas import ContractModel
from app.core.security import Principal, Role, get_principal

MODULES: tuple[str, ...] = (
    "overview",
    "machine",
    "component",
    "analysis",
    "baselines",
    "maintenance",
    "alarms",
    "datasource",
    "signals",
    "optimization",
    "models",
    "assistant",
)


class ModuleError(ValueError):
    pass


class RoleModulesRecord(Base):
    __tablename__ = "role_modules"

    role: Mapped[str] = mapped_column(String(16), primary_key=True)
    modules: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RoleModules(ContractModel):
    role: Role
    modules: list[str]
    editable: bool


class RoleModulesChange(ContractModel):
    modules: list[str] = Field(max_length=len(MODULES))


class ModuleStore:
    def __init__(self, session: Session):
        self.session = session

    def visible(self, role: Role) -> list[str]:
        if role == Role.ADMIN:
            return list(MODULES)
        r = self.session.get(RoleModulesRecord, role.value)
        if r is None:
            return list(MODULES)
        saved = set(r.modules)
        return [m for m in MODULES if m in saved]

    def all(self) -> list[RoleModules]:
        return [RoleModules(role=r, modules=self.visible(r), editable=r != Role.ADMIN) for r in Role]

    def set(self, role: Role, modules: list[str], who: Principal) -> RoleModules:
        if not who.at_least(Role.ADMIN):
            raise ModuleError("configuring modules requires an administrator")
        if role == Role.ADMIN:
            raise ModuleError("the administrator role always has every module")
        unknown = sorted(set(modules) - set(MODULES))
        if unknown:
            raise ModuleError(f"unknown modules: {', '.join(unknown)}")
        ordered = [m for m in MODULES if m in set(modules)]
        before = self.visible(role)
        r = self.session.get(RoleModulesRecord, role.value)
        if r is None:
            r = RoleModulesRecord(role=role.value, modules=ordered, updated_by=who.user_id)
            self.session.add(r)
        r.modules, r.updated_by, r.updated_at = ordered, who.user_id, datetime.now(UTC)
        added, removed = sorted(set(ordered) - set(before)), sorted(set(before) - set(ordered))
        audit(self.session, who, "role.modules", "role", role.value, added=added, removed=removed)
        self.session.commit()
        return RoleModules(role=role, modules=ordered, editable=True)


def require_module(*names: str) -> Any:
    """Dependency: the caller's role must have at least one of ``names`` visible."""
    for n in names:
        if n not in MODULES:
            raise ValueError(f"unknown module {n}")

    def check(
        principal: Annotated[Principal, Depends(get_principal)],
        session: Annotated[Session, Depends(get_session)],
    ) -> Principal:
        if not set(names) & set(ModuleStore(session).visible(principal.role)):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"module {' / '.join(names)} is not enabled for your role"
            )
        return principal

    return Depends(check)
