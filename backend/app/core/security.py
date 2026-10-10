"""Principal and roles (SEC-01).

Two providers, chosen by ``PDM_AUTH_MODE``:

- ``local`` (deployment, T028): signed session cookie from ``/api/auth/login``, account re-read on every
  request, ``X-PDM-CSRF`` header required on state-changing requests (see ``app.core.auth``).
- ``dev`` (development and tests only, D-010): the caller states user and role in ``X-PDM-User`` /
  ``X-PDM-Role``. It MUST NOT be used on a shared network.

Any other value refuses every request.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
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


UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def _local_principal(request: Request, session: Session) -> Principal:
    from app.core.auth import COOKIE, AuthError, UserStore, read_token

    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign-in required")
    try:
        principal = UserStore(session).principal(read_token(token, get_settings().secret_key))
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign-in required") from exc
    if request.method in UNSAFE and request.headers.get("x-pdm-csrf") != "1":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "missing X-PDM-CSRF header")
    return principal


def get_principal(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    x_pdm_user: Annotated[str | None, Header()] = None,
    x_pdm_role: Annotated[str | None, Header()] = None,
) -> Principal:
    mode = get_settings().auth_mode
    if mode == "local":
        return _local_principal(request, session)
    if mode != "dev":
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
