"""Principal and roles (SEC-01).

Full authentication arrives with deployment (T028). Until then the only provider is ``dev``: the
caller states user and role in ``X-PDM-User`` / ``X-PDM-Role`` headers. It exists so role checks and
audit attribution are real from the first API onward; it MUST NOT be enabled on a shared network
(``PDM_AUTH_MODE`` other than ``dev`` disables it). See DECISIONS D-010.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.core.config import get_settings
from app.core.schemas import ContractModel


class Role(StrEnum):
    VIEWER = "viewer"
    MAINTENANCE = "maintenance"
    ENGINEER = "engineer"
    ADMIN = "admin"


ROLE_RANK = {Role.VIEWER: 0, Role.MAINTENANCE: 1, Role.ENGINEER: 2, Role.ADMIN: 3}


class Principal(ContractModel):
    user_id: str
    role: Role

    def at_least(self, role: Role) -> bool:
        return ROLE_RANK[self.role] >= ROLE_RANK[role]


def get_principal(
    x_pdm_user: Annotated[str | None, Header()] = None,
    x_pdm_role: Annotated[str | None, Header()] = None,
) -> Principal:
    if get_settings().auth_mode != "dev":
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "authentication provider not configured")
    if not x_pdm_user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign-in required")
    try:
        role = Role(x_pdm_role or Role.VIEWER)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown role") from exc
    return Principal(user_id=x_pdm_user[:64], role=role)


def require(role: Role):
    """Dependency factory: the caller must hold ``role`` or higher."""

    def check(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if not principal.at_least(role):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires role {role.value}")
        return principal

    return check
