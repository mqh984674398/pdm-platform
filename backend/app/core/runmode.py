"""Run mode (D-053): the platform shows and uses either the simulation database or the production
TDengine sources, never both. Administrators switch it; the value is stored in the database and falls
back to ``PDM_RUN_MODE`` (default ``simulation``) until someone sets it. In production mode no screen
lists simulated machines, components, alarms, signals or data sources."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.audit import record as audit
from app.core.config import get_settings
from app.core.db import Base
from app.core.security import Principal, Role


class RunMode(StrEnum):
    SIMULATION = "simulation"
    PRODUCTION = "production"


class RunModePermissionError(PermissionError):
    pass


KEY = "run_mode"


class SettingRecord(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(200), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def get_mode(session: Session) -> RunMode:
    rec = session.get(SettingRecord, KEY)
    raw = rec.value if rec else get_settings().run_mode
    try:
        return RunMode(raw)
    except ValueError:
        return RunMode.SIMULATION


def set_mode(session: Session, mode: RunMode, who: Principal) -> RunMode:
    if who.role != Role.ADMIN:
        raise RunModePermissionError("only an administrator may change the run mode")
    before = get_mode(session)
    rec = session.get(SettingRecord, KEY)
    now = datetime.now(UTC)
    if rec is None:
        session.add(SettingRecord(key=KEY, value=mode.value, updated_by=who.user_id, updated_at=now))
    else:
        rec.value, rec.updated_by, rec.updated_at = mode.value, who.user_id, now
    audit(session, who, "settings.run_mode", "setting", KEY, before=before.value, after=mode.value)
    return mode
