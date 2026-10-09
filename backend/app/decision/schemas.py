"""L6 contracts: evidence, health decisions, recommendations, alarms."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field

from app.core.schemas import ContractModel, LocalizedText, ResultMeta
from app.equipment.schemas import ComponentLifecycle, ComponentType, MaintenanceEvent
from app.signals.schemas import SignalDefinition


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


class TrendPoint(ContractModel):
    ts: AwareDatetime
    value: float


class HealthTrend(ContractModel):
    """Persistent deviation of one statistical rule from the verified healthy reference, per window."""

    rule_id: str
    name: LocalizedText
    feature: str
    unit: str = "deviation"
    watch: float | None
    warning: float | None
    critical: float | None
    points: list[TrendPoint]


class FleetComponent(ContractModel):
    """One component on the dashboard: its current health output and what it is based on (UI-02/03)."""

    component_id: str
    machine_id: str
    type: ComponentType
    name: LocalizedText
    drive_chain_id: str | None
    health: HealthState
    reason: LocalizedText
    lifecycle_id: str | None
    last_window_end: AwareDatetime | None
    open_alarms: int
    lifecycles: list[ComponentLifecycle]
    maintenance: list[MaintenanceEvent]
    signals: list[SignalDefinition]
    trend: list[HealthTrend]
    is_simulated: bool


class FleetMachine(ContractModel):
    machine_id: str
    name: LocalizedText
    line: str | None
    as_of: AwareDatetime | None = Field(description="Newest evaluated window of the machine")
    components: list[FleetComponent]
    is_simulated: bool


class FleetOverview(ContractModel):
    machines: list[FleetMachine]
    health_basis: LocalizedText
    rules_version: str
    is_simulated: bool


class ComponentHealthReport(ContractModel):
    """Current health decision of a component with its evidence trail (L6-04)."""

    decision: Decision
    evidence: list[Evidence]
    recommendations: list[Recommendation] = Field(default_factory=list)
    is_simulated: bool


# Alarm contracts live with the rules that raise them (L4); re-exported here for L6 consumers.
from app.monitoring.schemas import Alarm, AlarmSeverity, AlarmStatus  # noqa: E402

__all__ = ["Alarm", "AlarmSeverity", "AlarmStatus"]
