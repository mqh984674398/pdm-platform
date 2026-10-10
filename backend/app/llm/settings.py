"""Ollama settings chosen by an administrator (LLM-01): endpoint, chat and embedding models, LAN allowlist.

Stored as audited, versioned rows; the newest row is in force. Every change re-validates the endpoint
and the models (local/LAN only, no cloud-routed models). Disabled by default, so the platform runs
without Ollama (GEN-04).
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import AwareDatetime, Field
from sqlalchemy import JSON, DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.audit import record as audit
from app.core.db import Base
from app.core.schemas import ContractModel
from app.core.security import Principal, Role
from app.llm.endpoint import validate_endpoint, validate_model


class LlmPermissionError(PermissionError):
    pass


class LlmConfig(ContractModel):
    enabled: bool = False
    endpoint: str = "http://127.0.0.1:11434"
    chat_model: str = ""
    embed_model: str = ""
    allowed_hosts: list[str] = Field(default_factory=list, description="LAN host names allowed besides IPs")
    allowed_models: list[str] = Field(default_factory=list, description="Empty: any installed local model")
    timeout_s: float = Field(default=60.0, gt=0, le=600)


class LlmConfigState(ContractModel):
    config: LlmConfig
    version: int
    changed_by: str | None
    changed_at: AwareDatetime | None


class LlmSettingRecord(Base):
    __tablename__ = "llm_settings"

    version: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    changed_by: Mapped[str] = mapped_column(String(64), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LlmSettings:
    def __init__(self, session: Session):
        self.session = session

    def current(self) -> LlmConfigState:
        row = self.session.scalars(select(LlmSettingRecord).order_by(LlmSettingRecord.version.desc())).first()
        if row is None:
            return LlmConfigState(config=LlmConfig(), version=0, changed_by=None, changed_at=None)
        at = row.changed_at if row.changed_at.tzinfo else row.changed_at.replace(tzinfo=UTC)
        return LlmConfigState(
            config=LlmConfig.model_validate(row.config),
            version=row.version,
            changed_by=row.changed_by,
            changed_at=at,
        )

    def update(self, cfg: LlmConfig, who: Principal) -> LlmConfigState:
        if not who.at_least(Role.ADMIN):
            raise LlmPermissionError("changing the Ollama settings requires an administrator")
        endpoint = validate_endpoint(cfg.endpoint, cfg.allowed_hosts)
        for m in (cfg.chat_model, cfg.embed_model):
            if m:
                validate_model(m, cfg.allowed_models)
        cfg = cfg.model_copy(update={"endpoint": endpoint})
        self.session.add(
            LlmSettingRecord(
                config=cfg.model_dump(mode="json"), changed_by=who.user_id, changed_at=datetime.now(UTC)
            )
        )
        audit(self.session, who, "llm.settings", "llm", "settings", **cfg.model_dump(mode="json"))
        self.session.commit()
        return self.current()
