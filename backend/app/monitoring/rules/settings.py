"""Rule settings: which rules of the versioned rule set are enabled (L6-03, OPT-05).

Thresholds are part of the rule set version and are not editable here. Disabling or re-enabling a
safety rule needs an administrator; statistical rules need an engineer. Every change needs a comment,
is audited, and bumps the configuration version that evaluations and alarms carry.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.audit import record as audit
from app.core.db import Base
from app.core.security import Principal, Role
from app.equipment.lifecycle import _aware
from app.monitoring.rules.definitions import DEFAULT_RULES
from app.monitoring.schemas import RuleChange, RuleKind, RuleSet, RuleSetStatus, RuleState


class RuleNotFoundError(KeyError):
    pass


class RulePermissionError(PermissionError):
    pass


class RuleSettingRecord(Base):
    __tablename__ = "rule_settings"

    change_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_set: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    rule_id: Mapped[str] = mapped_column(String(40), nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False)
    changed_by: Mapped[str] = mapped_column(String(64), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    comment: Mapped[str] = mapped_column(String(2000), nullable=False)


class RuleSettings:
    def __init__(self, session: Session, rules: RuleSet = DEFAULT_RULES):
        self.session = session
        self.rules = rules

    def _latest(self) -> dict[str, RuleSettingRecord]:
        stmt = (
            select(RuleSettingRecord)
            .where(RuleSettingRecord.rule_set == self.rules.ref)
            .order_by(RuleSettingRecord.change_id)
        )
        return {r.rule_id: r for r in self.session.scalars(stmt)}

    def config_version(self) -> str:
        n = self.session.scalar(
            select(func.count())
            .select_from(RuleSettingRecord)
            .where(RuleSettingRecord.rule_set == self.rules.ref)
        )
        return f"{self.rules.ref}+{n or 0}"

    def disabled(self) -> set[str]:
        return {rid for rid, r in self._latest().items() if not r.enabled}

    def status(self) -> RuleSetStatus:
        latest = self._latest()
        states = []
        for rule in self.rules.rules:
            r = latest.get(rule.rule_id)
            states.append(
                RuleState(
                    rule_id=rule.rule_id,
                    kind=rule.kind,
                    enabled=r.enabled if r else True,
                    changed_by=r.changed_by if r else None,
                    changed_at=_aware(r.changed_at) if r else None,
                    comment=r.comment if r else "",
                )
            )
        return RuleSetStatus(rule_set=self.rules, states=states, config_version=self.config_version())

    def change(
        self, rule_id: str, req: RuleChange, who: Principal, now: datetime | None = None
    ) -> RuleSetStatus:
        rule = next((r for r in self.rules.rules if r.rule_id == rule_id), None)
        if rule is None:
            raise RuleNotFoundError(rule_id)
        need = Role.ADMIN if rule.kind == RuleKind.SAFETY else Role.ENGINEER
        if not who.at_least(need):
            raise RulePermissionError(f"changing {rule.kind.value.lower()} rules requires {need.value}")
        self.session.add(
            RuleSettingRecord(
                rule_set=self.rules.ref,
                rule_id=rule_id,
                enabled=req.enabled,
                changed_by=who.user_id,
                changed_at=now or datetime.now(UTC),
                comment=req.comment.strip(),
            )
        )
        audit(
            self.session,
            who,
            "rule.enable" if req.enabled else "rule.disable",
            "rule",
            rule_id,
            rule_set=self.rules.ref,
            kind=rule.kind.value,
            comment=req.comment.strip(),
        )
        self.session.flush()
        return self.status()
