"""Sign-in and account management (SEC-01, T028).

``POST /auth/login`` sets the session cookie (local mode only); ``/auth/me`` reports who is signed in
and the provider in use, so the browser can show sign-in or the development role selector.
Account management needs an administrator.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field
from sqlalchemy.orm import Session

from app.core.auth import COOKIE, SESSION_HOURS, NewUser, UserChange, UserInfo, UserStore, issue_token
from app.core.config import get_settings
from app.core.db import get_session
from app.core.schemas import ContractModel
from app.core.security import Principal, Role, get_principal, require

router = APIRouter(tags=["auth"])
DB = Annotated[Session, Depends(get_session)]
Admin = Annotated[Principal, Depends(require(Role.ADMIN))]


class Login(ContractModel):
    user_id: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


class Me(ContractModel):
    user_id: str
    role: Role
    mode: str


@router.post("/auth/login", response_model=Me)
def login(body: Login, response: Response, db: DB) -> Me:
    s = get_settings()
    if s.auth_mode != "local":
        raise HTTPException(409, "sign-in is only used with PDM_AUTH_MODE=local")
    p = UserStore(db).login(body.user_id, body.password)
    response.set_cookie(
        COOKIE,
        issue_token(p.user_id, s.secret_key),
        max_age=SESSION_HOURS * 3600,
        httponly=True,
        samesite="strict",
        secure=s.cookie_secure,
        path="/",
    )
    return Me(user_id=p.user_id, role=p.role, mode=s.auth_mode)


@router.post("/auth/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


@router.get("/auth/me", response_model=Me)
def me(who: Annotated[Principal, Depends(get_principal)]) -> Me:
    return Me(user_id=who.user_id, role=who.role, mode=get_settings().auth_mode)


@router.get("/auth/users", response_model=list[UserInfo])
def users(_: Admin, db: DB) -> list[UserInfo]:
    return UserStore(db).users()


@router.post("/auth/users", response_model=UserInfo)
def create_user(body: NewUser, who: Admin, db: DB) -> UserInfo:
    return UserStore(db).create(body, who)


@router.put("/auth/users/{user_id}", response_model=UserInfo)
def change_user(user_id: str, body: UserChange, who: Admin, db: DB) -> UserInfo:
    return UserStore(db).change(user_id, body, who)
