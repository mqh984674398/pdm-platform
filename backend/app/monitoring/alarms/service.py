"""Alarm events from rule evaluations, and their lifecycle (UI-09), audited.

``sync`` walks evaluations in time order, once per window (a watermark per component makes repeated
calls idempotent). A rule firing with no open alarm for that component and rule raises one; a higher
level escalates the open alarm; a window where the rule no longer fires marks the condition cleared
(and a later firing marks it active again). Only people move an alarm: RAISED -> ACKNOWLEDGED ->
RESOLVED, or RAISED -> RESOLVED; resolving needs a comment. After resolution, a rule that still fires
raises a new alarm. Alarms are records for review: nothing here sends a notification, and no official
maintenance-alerting workflow is enabled.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.audit import record as audit
from app.core.db import Base
from app.core.schemas import LocalizedText
from app.core.security import Principal
from app.equipment.lifecycle import _aware
from app.monitoring.rules.definitions import DEFAULT_RULES
from app.monitoring.schemas import (
    Alarm,
    AlarmSeverity,
    AlarmStatus,
    MonitoringLevel,
    RuleHit,
    RuleKind,
    RuleSet,
    SafetyStatus,
    WindowEvaluation,
)

ORDER = [AlarmSeverity.WATCH, AlarmSeverity.WARNING, AlarmSeverity.CRITICAL]
OPEN = (AlarmStatus.RAISED.value, AlarmStatus.ACKNOWLEDGED.value)


class AlarmNotFoundError(KeyError):
    pass


class AlarmTransitionError(ValueError):
    pass


class AlarmRecord(Base):
    __tablename__ = "alarms"

    alarm_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    component_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    lifecycle_id: Mapped[str] = mapped_column(String(80), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolution_comment: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    condition_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    last_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    message: Mapped[dict] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    rules_version: Mapped[str] = mapped_column(String(100), nullable=False)
    is_simulated: Mapped[bool] = mapped_column(nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __mapper_args__ = {"version_id_col": revision}

    def to_model(self) -> Alarm:
        return Alarm(
            alarm_id=self.alarm_id,
            component_id=self.component_id,
            lifecycle_id=self.lifecycle_id,
            severity=AlarmSeverity(self.severity),
            status=AlarmStatus(self.status),
            rule_id=self.rule_id,
            raised_at=_aware(self.raised_at),
            acknowledged_at=_aware(self.acknowledged_at),
            acknowledged_by=self.acknowledged_by,
            resolved_at=_aware(self.resolved_at),
            resolved_by=self.resolved_by,
            resolution_comment=self.resolution_comment,
            condition_active=self.condition_active,
            last_window_end=_aware(self.last_window_end),
            message=LocalizedText.model_validate(self.message),
            evidence_ids=list(self.evidence_ids),
            rules_version=self.rules_version,
            is_simulated=self.is_simulated,
        )


class AlarmWatermark(Base):
    __tablename__ = "alarm_watermarks"

    component_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    evaluated_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


DEGRADED_PREFIX = "DQ:"  # alarm rule id of a safety check that could not be evaluated


def evidence_id(rule_id: str, e: WindowEvaluation) -> str:
    return f"RH:{rule_id}:{e.component_id}:{e.window.start.isoformat()}"


class AlarmService:
    def __init__(self, session: Session, rules: RuleSet = DEFAULT_RULES):
        self.session = session
        self.rules = {r.rule_id: r for r in rules.rules}

    def _open(self, component_id: str, rule_id: str) -> AlarmRecord | None:
        stmt = select(AlarmRecord).where(
            AlarmRecord.component_id == component_id,
            AlarmRecord.rule_id == rule_id,
            AlarmRecord.status.in_(OPEN),
        )
        return self.session.scalar(stmt)

    def sync(self, evaluations: Sequence[WindowEvaluation], who: Principal) -> tuple[list[str], list[str]]:
        """Returns (raised, updated) alarm ids."""
        raised: list[str] = []
        updated: list[str] = []
        marks: dict[str, AlarmWatermark] = {}
        for e in sorted(evaluations, key=lambda e: (e.component_id, e.window.end)):
            mark = marks.get(e.component_id) or self.session.get(AlarmWatermark, e.component_id)
            if mark is not None:
                marks[e.component_id] = mark
                if e.window.end <= _aware(mark.evaluated_until):
                    continue
            firing = {h.rule_id: h for h in e.hits}
            for rid, st in e.safety_checks.items():  # D-043: a degraded safety check is reported, not hidden
                if st == SafetyStatus.NOT_EVALUATED:
                    firing[f"{DEGRADED_PREFIX}{rid}"] = RuleHit(
                        rule_id=f"{DEGRADED_PREFIX}{rid}",
                        kind=RuleKind.SAFETY,
                        level=MonitoringLevel.WATCH,
                        feature="measurement",
                        value=0.0,
                        threshold=0.0,
                        basis="quality",
                    )
            rule_ids = set(firing) | {
                r.rule_id
                for r in self.session.scalars(
                    select(AlarmRecord).where(
                        AlarmRecord.component_id == e.component_id, AlarmRecord.status.in_(OPEN)
                    )
                )
            }
            for rid in sorted(rule_ids):
                open_ = self._open(e.component_id, rid)
                hit = firing.get(rid)
                if hit is not None and hit.level != MonitoringLevel.NORMAL:
                    sev = AlarmSeverity(hit.level.value)
                    if open_ is None:
                        rule = self.rules.get(rid)
                        if rid.startswith(DEGRADED_PREFIX):
                            base = rid[len(DEGRADED_PREFIX) :]
                            msg = LocalizedText(
                                zh=f"安全监测降级：{base} 所需测量缺失或无效，无法确认是否违限（不等于正常）",
                                en=f"Safety monitoring degraded: {base} measurement missing or invalid; "
                                "a violation cannot be confirmed (not the same as normal)",
                            )
                        else:
                            msg = rule.description if rule else LocalizedText(zh=rid, en=rid)
                        rec = AlarmRecord(
                            alarm_id=f"AL-{uuid.uuid4().hex[:16]}",
                            component_id=e.component_id,
                            lifecycle_id=e.lifecycle_id,
                            rule_id=rid,
                            severity=sev.value,
                            status=AlarmStatus.RAISED.value,
                            raised_at=e.window.end,
                            condition_active=True,
                            last_window_end=e.window.end,
                            message=msg.model_dump(),
                            evidence_ids=[evidence_id(rid, e)],
                            rules_version=e.rules_version,
                            is_simulated=e.is_simulated,
                        )
                        self.session.add(rec)
                        self.session.flush()
                        raised.append(rec.alarm_id)
                        audit(self.session, who, "alarm.raise", "alarm", rec.alarm_id, rule_id=rid,
                              severity=sev.value, component_id=e.component_id,
                              window_end=e.window.end.isoformat(), value=hit.value)  # fmt: skip
                        continue
                    changed = False
                    if ORDER.index(sev) > ORDER.index(AlarmSeverity(open_.severity)):
                        audit(self.session, who, "alarm.escalate", "alarm", open_.alarm_id,
                              from_severity=open_.severity, to_severity=sev.value,
                              window_end=e.window.end.isoformat(), value=hit.value)  # fmt: skip
                        open_.severity, changed = sev.value, True
                    if not open_.condition_active:
                        audit(self.session, who, "alarm.reactivate", "alarm", open_.alarm_id,
                              window_end=e.window.end.isoformat())  # fmt: skip
                        open_.condition_active, changed = True, True
                    eid = evidence_id(rid, e)
                    if changed:
                        open_.evidence_ids = [*open_.evidence_ids, eid]
                        updated.append(open_.alarm_id)
                    open_.last_window_end = e.window.end
                elif open_ is not None and open_.condition_active and rid not in e.not_evaluated:
                    open_.condition_active, open_.last_window_end = False, e.window.end
                    audit(self.session, who, "alarm.clear", "alarm", open_.alarm_id,
                          window_end=e.window.end.isoformat())  # fmt: skip
                    updated.append(open_.alarm_id)
            if mark is None:
                mark = AlarmWatermark(component_id=e.component_id, evaluated_until=e.window.end)
                self.session.add(mark)
                marks[e.component_id] = mark
            else:
                mark.evaluated_until = e.window.end
            self.session.flush()
        return raised, sorted(set(updated) - set(raised))

    def alarms(self, component_id: str | None = None, status: AlarmStatus | None = None) -> list[Alarm]:
        stmt = select(AlarmRecord).order_by(AlarmRecord.raised_at, AlarmRecord.alarm_id)
        if component_id:
            stmt = stmt.where(AlarmRecord.component_id == component_id)
        if status:
            stmt = stmt.where(AlarmRecord.status == status.value)
        return [r.to_model() for r in self.session.scalars(stmt)]

    def _get(self, alarm_id: str) -> AlarmRecord:
        rec = self.session.get(AlarmRecord, alarm_id)
        if rec is None:
            raise AlarmNotFoundError(alarm_id)
        return rec

    def acknowledge(
        self, alarm_id: str, who: Principal, comment: str = "", now: datetime | None = None
    ) -> Alarm:
        rec = self._get(alarm_id)
        if rec.status != AlarmStatus.RAISED.value:
            raise AlarmTransitionError(f"alarm is {rec.status}; only a raised alarm can be acknowledged")
        rec.status, rec.acknowledged_at, rec.acknowledged_by = (
            AlarmStatus.ACKNOWLEDGED.value,
            now or datetime.now(UTC),
            who.user_id,
        )
        audit(self.session, who, "alarm.acknowledge", "alarm", alarm_id, comment=comment.strip())
        self.session.flush()
        return rec.to_model()

    def resolve(self, alarm_id: str, who: Principal, comment: str, now: datetime | None = None) -> Alarm:
        rec = self._get(alarm_id)
        if rec.status == AlarmStatus.RESOLVED.value:
            raise AlarmTransitionError("alarm is already resolved")
        if not comment.strip():
            raise AlarmTransitionError("resolving an alarm needs a comment with the outcome")
        rec.status, rec.resolved_at, rec.resolved_by = (
            AlarmStatus.RESOLVED.value,
            now or datetime.now(UTC),
            who.user_id,
        )
        rec.resolution_comment = comment.strip()
        audit(self.session, who, "alarm.resolve", "alarm", alarm_id, comment=comment.strip(),
              condition_active=rec.condition_active)  # fmt: skip
        self.session.flush()
        return rec.to_model()
