"""L6 contracts: evidence, health decisions, recommendations, alarms."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field, computed_field

from app.core.schemas import ContractModel, LocalizedText, ResultMeta
from app.equipment.schemas import ComponentLifecycle, ComponentType, MaintenanceEvent
from app.monitoring.schemas import SafetyStatus
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


class EvidenceType(StrEnum):
    SAFETY = "SAFETY"
    STATISTICAL = "STATISTICAL"
    ANOMALY = "ANOMALY"  # unsupervised anomaly detection and degradation indicators
    SUPERVISED = "SUPERVISED"
    CONTEXT = "CONTEXT"  # reference, open alarm or maintenance impact shown for lineage; never a verdict


class QualityStatus(StrEnum):
    OK = "OK"
    INVALID = "INVALID"  # the input data failed validation or is missing
    NOT_EVALUATED = "NOT_EVALUATED"


class Evidence(ContractModel):
    """Unified evidence object (D-043). Every rule, statistic and model reports in this shape; the
    decision never adds raw scores of different algorithms. ``applicable``, ``reason``, ``model_version``,
    ``evaluated_at`` and ``input_window_id`` are derived from the stored fields so they cannot disagree."""

    evidence_id: str
    component_id: str
    evidence_type: EvidenceType
    source: EvidenceSource
    result_ref: str = Field(description="Id of the underlying result (prediction, rule hit, report)")
    summary: LocalizedText
    eligible: bool
    meta: ResultMeta
    raw_value: float | None = Field(default=None, description="Original algorithm score or measurement")
    threshold: float | None = Field(default=None, description="Decision threshold, when there is one")
    calibration: str | None = Field(default=None, description="Calibration version, when there is one")
    proposed_severity: HealthState | None = Field(
        default=None, description="Severity this evidence proposes; None when it proposes none"
    )
    quality_status: QualityStatus = QualityStatus.OK
    baseline_version: str | None = Field(default=None, description="Healthy reference the evidence used")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def applicable(self) -> bool:
        return self.eligible

    @computed_field  # type: ignore[prop-decorator]
    @property
    def reason(self) -> LocalizedText:
        return self.summary

    @computed_field  # type: ignore[prop-decorator]
    @property
    def model_version(self) -> str:
        return self.meta.model_version

    @computed_field  # type: ignore[prop-decorator]
    @property
    def evaluated_at(self) -> AwareDatetime:
        return self.meta.computed_at

    @computed_field  # type: ignore[prop-decorator]
    @property
    def input_window_id(self) -> str:
        w = self.meta.data_window
        return f"{self.component_id}:{w.start.isoformat()}/{w.end.isoformat()}"


class Decision(ContractModel):
    decision_id: str
    component_id: str
    lifecycle_id: str
    health_state: HealthState
    reasons: list[LocalizedText] = Field(min_length=1)
    evidence_ids: list[str]
    safety_constraints_applied: list[str] = Field(default_factory=list)
    safety_status: SafetyStatus = Field(
        default=SafetyStatus.NOT_EVALUATED,
        description="Violation confirmed, check not evaluable, normal confirmed, or no check configured",
    )
    safety_unevaluated: list[str] = Field(
        default_factory=list, description="Safety rules whose measurement is missing or invalid"
    )
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


class CommonCause(ContractModel):
    """Two or more components on one shared drive chain are abnormal at the same time (S19, D-038).

    The drive chain is the likelier single cause than separate wear of each component, so it is
    pointed out next to each component's own health output. Health states themselves are unchanged."""

    drive_chain_id: str
    component_ids: list[str] = Field(min_length=2)
    note: LocalizedText


class FleetComponent(ContractModel):
    """One component on the dashboard: its current health output and what it is based on (UI-02/03)."""

    component_id: str
    machine_id: str
    type: ComponentType
    name: LocalizedText
    drive_chain_id: str | None
    health: HealthState
    reason: LocalizedText
    common_cause: CommonCause | None = None
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
    path: LocalizedText | None = Field(default=None, description="Workshop / process (D-037)")
    as_of: AwareDatetime | None = Field(description="Newest evaluated window of the machine")
    components: list[FleetComponent]
    is_simulated: bool


class FleetOverview(ContractModel):
    machines: list[FleetMachine]
    health_basis: LocalizedText
    rules_version: str
    is_simulated: bool


class Display(ContractModel):
    own_status: bool = True
    related_status: bool = True
    trend: bool = True
    evidence: bool = True
    recommendations: bool = True
    alarms: bool = True


class RelatedStatus(ContractModel):
    """Health of a component the configuration relates to this one (shown when the relationship says so)."""

    component_id: str
    relation: str
    health: HealthState


class ComponentHealthReport(ContractModel):
    """Current health decision of a component with its evidence trail (L6-04)."""

    decision: Decision
    evidence: list[Evidence]
    recommendations: list[Recommendation] = Field(default_factory=list)
    common_cause: CommonCause | None = None
    is_simulated: bool
    config_version: str | None = Field(default=None, description="Active prediction configuration, if any")
    display: Display | None = None
    related: list[RelatedStatus] = Field(default_factory=list)


# Alarm contracts live with the rules that raise them (L4); re-exported here for L6 consumers.
from app.monitoring.schemas import Alarm, AlarmSeverity, AlarmStatus  # noqa: E402

__all__ = ["Alarm", "AlarmSeverity", "AlarmStatus"]
