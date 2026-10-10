"""Local sign-in for LAN deployment (SEC-01, T028; replaces the development header provider).

Accounts live in the ``users`` table with scrypt password hashes. A successful sign-in sets an
HttpOnly, SameSite=Strict session cookie holding ``user|issued|expiry`` signed with HMAC-SHA256 and the
server secret (``PDM_SECRET_KEY``). Every request re-reads the account, so deactivation and role
changes apply at once. State-changing requests must also carry ``X-PDM-CSRF: 1`` (a custom header a
cross-site form cannot send). Five failed attempts lock an account for five minutes. Sign-ins,
failures and account changes are audited.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from datetime import UTC, datetime, timedelta

from pydantic import AwareDatetime, Field
from sqlalchemy import Boolean, DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.audit import record as audit
from app.core.db import Base
from app.core.schemas import ContractModel
from app.core.security import Principal, Role

COOKIE = "pdm_session"
SESSION_HOURS = 12
MAX_FAILURES, LOCK_MINUTES = 5, 5
MIN_PASSWORD = 10
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


class AuthError(PermissionError):
    pass


class AccountError(ValueError):
    pass


class UserRecord(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserInfo(ContractModel):
    user_id: str
    display_name: str
    role: Role
    active: bool
    created_at: AwareDatetime


class NewUser(ContractModel):
    user_id: str = Field(pattern=r"^[a-zA-Z0-9._-]{2,64}$")
    display_name: str = Field(min_length=1, max_length=120)
    role: Role
    password: str = Field(min_length=MIN_PASSWORD, max_length=200)


class UserChange(ContractModel):
    role: Role | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=MIN_PASSWORD, max_length=200)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt, dk = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), **_SCRYPT)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, base64.b64decode(dk))


def _sig(secret: str, payload: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def issue_token(user_id: str, secret: str, now: float | None = None) -> str:
    t = int(now or time.time())
    payload = f"{user_id}|{t}|{t + SESSION_HOURS * 3600}"
    return f"{payload}|{_sig(secret, payload)}"


def read_token(token: str, secret: str, now: float | None = None) -> str:
    try:
        user_id, issued, expiry, sig = token.split("|")
    except ValueError as e:
        raise AuthError("malformed session") from e
    if not hmac.compare_digest(sig, _sig(secret, f"{user_id}|{issued}|{expiry}")):
        raise AuthError("invalid session")
    if int(expiry) < int(now or time.time()):
        raise AuthError("session expired")
    return user_id


def _aware(t: datetime | None) -> datetime | None:
    return t if t is None or t.tzinfo else t.replace(tzinfo=UTC)


class UserStore:
    def __init__(self, session: Session):
        self.session = session

    def _info(self, r: UserRecord) -> UserInfo:
        return UserInfo(
            user_id=r.user_id,
            display_name=r.display_name,
            role=Role(r.role),
            active=r.active,
            created_at=_aware(r.created_at),
        )

    def users(self) -> list[UserInfo]:
        return [self._info(r) for r in self.session.scalars(select(UserRecord).order_by(UserRecord.user_id))]

    def principal(self, user_id: str) -> Principal:
        r = self.session.get(UserRecord, user_id)
        if r is None or not r.active:
            raise AuthError("account not found or deactivated")
        return Principal(user_id=r.user_id, role=Role(r.role))

    def create(self, u: NewUser, who: Principal) -> UserInfo:
        if not who.at_least(Role.ADMIN):
            raise AuthError("managing accounts requires an administrator")
        if self.session.get(UserRecord, u.user_id) is not None:
            raise AccountError(f"account {u.user_id} already exists")
        r = UserRecord(
            user_id=u.user_id,
            display_name=u.display_name,
            role=u.role.value,
            password_hash=hash_password(u.password),
            active=True,
            failed=0,
            created_at=datetime.now(UTC),
        )
        self.session.add(r)
        audit(self.session, who, "user.create", "user", u.user_id, role=u.role.value)
        self.session.commit()
        return self._info(r)

    def change(self, user_id: str, ch: UserChange, who: Principal) -> UserInfo:
        if not who.at_least(Role.ADMIN):
            raise AuthError("managing accounts requires an administrator")
        r = self.session.get(UserRecord, user_id)
        if r is None:
            raise AccountError(f"no account {user_id}")
        if user_id == who.user_id and (ch.active is False or (ch.role and ch.role != Role.ADMIN)):
            raise AccountError("you cannot deactivate or demote your own account")
        if ch.role is not None:
            r.role = ch.role.value
        if ch.active is not None:
            r.active = ch.active
        if ch.password is not None:
            r.password_hash, r.failed, r.locked_until = hash_password(ch.password), 0, None
        audit(
            self.session,
            who,
            "user.change",
            "user",
            user_id,
            role=ch.role and ch.role.value,
            active=ch.active,
            password_reset=ch.password is not None,
        )
        self.session.commit()
        return self._info(r)

    def login(self, user_id: str, password: str) -> Principal:
        r = self.session.get(UserRecord, user_id)
        now = datetime.now(UTC)
        actor = Principal(user_id=user_id[:64] or "unknown", role=Role.VIEWER)
        if r is not None and _aware(r.locked_until) and _aware(r.locked_until) > now:
            audit(self.session, actor, "auth.locked", "user", user_id)
            self.session.commit()
            raise AuthError("account temporarily locked after failed sign-ins")
        if r is None or not r.active or not check_password(password, r.password_hash):
            if r is not None:
                r.failed += 1
                if r.failed >= MAX_FAILURES:
                    r.locked_until, r.failed = now + timedelta(minutes=LOCK_MINUTES), 0
            audit(self.session, actor, "auth.failed", "user", user_id)
            self.session.commit()
            raise AuthError("wrong user name or password")
        r.failed, r.locked_until = 0, None
        p = Principal(user_id=r.user_id, role=Role(r.role))
        audit(self.session, p, "auth.login", "user", user_id)
        self.session.commit()
        return p
