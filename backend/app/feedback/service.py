"""User feedback on alarms, decisions, maintenance records and assistant answers (FB-01).

Feedback goes to a review queue. It never changes alarms, health or baselines, and it is never written
into verified healthy training data: only an engineer's explicit verification creates a reference.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.audit import record as audit
from app.core.db import Base
from app.core.schemas import ContractModel
from app.core.security import Principal, Role
from app.feedback.schemas import FeedbackVerdict


class FeedbackPermissionError(PermissionError):
    pass


class FeedbackNotFoundError(KeyError):
    pass


class FeedbackIn(ContractModel):
    alarm_id: str | None = None
    decision_id: str | None = None
    maintenance_event_id: str | None = None
    assistant_ref: str | None = Field(default=None, max_length=200)
    verdict: FeedbackVerdict
    comment: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def _target(self) -> FeedbackIn:
        if not any((self.alarm_id, self.decision_id, self.maintenance_event_id, self.assistant_ref)):
            raise ValueError(
                "feedback must refer to an alarm, decision, maintenance record or assistant answer"
            )
        return self


class FeedbackItem(FeedbackIn):
    feedback_id: str
    submitted_by: str
    submitted_at: AwareDatetime
    status: str = Field(description="PENDING_REVIEW or REVIEWED")
    reviewed_by: str | None = None
    review_note: str = ""


class FeedbackRecord(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alarm_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    decision_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    maintenance_event_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    assistant_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    submitted_by: Mapped[str] = mapped_column(String(64), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING_REVIEW")
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_note: Mapped[str] = mapped_column(String(2000), nullable=False, default="")

    def to_model(self) -> FeedbackItem:
        at = self.submitted_at if self.submitted_at.tzinfo else self.submitted_at.replace(tzinfo=UTC)
        return FeedbackItem(
            feedback_id=f"FB-{self.id}",
            alarm_id=self.alarm_id,
            decision_id=self.decision_id,
            maintenance_event_id=self.maintenance_event_id,
            assistant_ref=self.assistant_ref,
            verdict=FeedbackVerdict(self.verdict),
            comment=self.comment,
            submitted_by=self.submitted_by,
            submitted_at=at,
            status=self.status,
            reviewed_by=self.reviewed_by,
            review_note=self.review_note,
        )


class FeedbackService:
    def __init__(self, session: Session):
        self.session = session

    def submit(self, fb: FeedbackIn, who: Principal) -> FeedbackItem:
        if not who.at_least(Role.MAINTENANCE):
            raise FeedbackPermissionError("giving feedback requires the maintenance role")
        row = FeedbackRecord(
            alarm_id=fb.alarm_id,
            decision_id=fb.decision_id,
            maintenance_event_id=fb.maintenance_event_id,
            assistant_ref=fb.assistant_ref,
            verdict=fb.verdict.value,
            comment=fb.comment,
            submitted_by=who.user_id,
            submitted_at=datetime.now(UTC),
            status="PENDING_REVIEW",
        )
        self.session.add(row)
        self.session.flush()
        audit(self.session, who, "feedback.submit", "feedback", f"FB-{row.id}", verdict=fb.verdict.value)
        self.session.commit()
        return row.to_model()

    def items(self, status: str | None = None, alarm_id: str | None = None) -> list[FeedbackItem]:
        stmt = select(FeedbackRecord).order_by(FeedbackRecord.id)
        if status:
            stmt = stmt.where(FeedbackRecord.status == status)
        if alarm_id:
            stmt = stmt.where(FeedbackRecord.alarm_id == alarm_id)
        return [r.to_model() for r in self.session.scalars(stmt)]

    def review(self, feedback_id: str, note: str, who: Principal) -> FeedbackItem:
        if not who.at_least(Role.ENGINEER):
            raise FeedbackPermissionError("reviewing feedback requires an engineer")
        pk = feedback_id.removeprefix("FB-")
        row = self.session.get(FeedbackRecord, int(pk)) if pk.isdigit() else None
        if row is None:
            raise FeedbackNotFoundError(feedback_id)
        row.status, row.reviewed_by, row.review_note = "REVIEWED", who.user_id, note
        audit(self.session, who, "feedback.review", "feedback", feedback_id, note=note)
        self.session.commit()
        return row.to_model()
