"""L7 contracts: user feedback on alarms and decisions (FB-01).

Feedback feeds human review. It is never written directly into verified healthy training data.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime

from app.core.schemas import ContractModel


class FeedbackVerdict(StrEnum):
    CONFIRMED = "CONFIRMED"
    FALSE_ALARM = "FALSE_ALARM"
    UNSURE = "UNSURE"


class Feedback(ContractModel):
    feedback_id: str
    alarm_id: str | None = None
    decision_id: str | None = None
    verdict: FeedbackVerdict
    comment: str = ""
    submitted_by: str
    submitted_at: AwareDatetime
    maintenance_event_id: str | None = None
