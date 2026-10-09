"""L6 contracts: evidence, health decisions, recommendations, alarms."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field

from app.core.schemas import ContractModel, LocalizedText, ResultMeta


class HealthState(StrEnum):
    """Prediction output (L6-04). Never used as a self-generated training label."""

    NORMAL = "NORMAL"
    WATCH = "WATCH"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class EvidenceSource(StrEnum):
    RULE = "RULE"
    STATISTIC = "STATISTIC"
    MODEL = "MODEL"
    MAINTENANCE = "MAINTENANCE"
    DATA_QUALITY = "DATA_QUALITY"


class Evidence(ContractModel):
    evidence_id: str
    source: EvidenceSource
    result_ref: str = Field(description="Id of the underlying result (prediction, rule hit, report)")
    summary: LocalizedText
    eligible: bool
    meta: ResultMeta


class Decision(ContractModel):
    decision_id: str
    component_id: str
    lifecycle_id: str
    health_state: HealthState
    reasons: list[LocalizedText] = Field(min_length=1)
    evidence_ids: list[str]
    safety_constraints_applied: list[str] = Field(default_factory=list)
    conflicting_evidence: bool = False
    meta: ResultMeta


class RecommendationPriority(StrEnum):
    INFO = "INFO"
    PLAN = "PLAN"
    SOON = "SOON"
    IMMEDIATE = "IMMEDIATE"


class Recommendation(ContractModel):
    recommendation_id: str
    decision_id: str
    priority: RecommendationPriority
    action: LocalizedText
    rationale: LocalizedText
    evidence_ids: list[str] = Field(min_length=1)


class AlarmSeverity(StrEnum):
    WATCH = "WATCH"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlarmStatus(StrEnum):
    RAISED = "RAISED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class Alarm(ContractModel):
    alarm_id: str
    component_id: str
    lifecycle_id: str
    severity: AlarmSeverity
    status: AlarmStatus
    rule_id: str
    raised_at: AwareDatetime
    acknowledged_at: AwareDatetime | None = None
    resolved_at: AwareDatetime | None = None
    message: LocalizedText
    evidence_ids: list[str] = Field(min_length=1)
    is_simulated: bool
