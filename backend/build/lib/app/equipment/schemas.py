"""L3 contracts: topology, operating state, regimes, cycles, maintenance, lifecycles."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field, model_validator

from app.core.schemas import ContractModel, LocalizedText, TimeWindow


class ComponentType(StrEnum):
    BALL_SCREW = "BALL_SCREW"
    LINEAR_MOTOR = "LINEAR_MOTOR"
    VACUUM_CUP = "VACUUM_CUP"
    PNEUMATIC_CYLINDER = "PNEUMATIC_CYLINDER"
    CAM = "CAM"
    GEAR = "GEAR"


# Cam and gear have no telemetry yet: extensible templates only (REQUIREMENTS §14).
TEMPLATE_ONLY_TYPES = frozenset({ComponentType.CAM, ComponentType.GEAR})


class Machine(ContractModel):
    machine_id: str
    name: LocalizedText
    line: str | None = None
    is_simulated: bool
    process_id: str | None = Field(
        default=None, description="Process (工序) node in the plant structure; set by administrators"
    )
    device_id: str | None = Field(
        default=None, description="Device id of this machine in the data source (e.g. a TDengine tag)"
    )
    path: LocalizedText | None = Field(
        default=None, description="Workshop / process path, derived from the plant structure (read-only)"
    )


class ComponentInstance(ContractModel):
    component_id: str
    machine_id: str
    type: ComponentType
    name: LocalizedText
    drive_chain_id: str | None = Field(
        default=None, description="Components sharing a drive chain (scenario S19) share this id"
    )
    signal_ids: list[str] = Field(default_factory=list)
    torque_limit: float | None = Field(
        default=None,
        gt=0,
        description="Allowed torque in the unit of the component's torque signal; enables SF-TORQUE-LIMIT",
    )


class LifecycleStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class ComponentLifecycle(ContractModel):
    """One physical installation of a component. Replacement creates a new lifecycle (L3-06)."""

    lifecycle_id: str
    component_id: str
    installed_at: AwareDatetime
    retired_at: AwareDatetime | None = None
    predecessor_lifecycle_id: str | None = None
    status: LifecycleStatus
    accumulated_operating_hours: float = Field(default=0, ge=0)
    accumulated_cycles: int = Field(default=0, ge=0)
    usage_counted_until: AwareDatetime | None = Field(
        default=None, description="Operation up to this time is included in the accumulated values"
    )

    @model_validator(mode="after")
    def _retired_consistent(self) -> ComponentLifecycle:
        if (self.status == LifecycleStatus.RETIRED) != (self.retired_at is not None):
            raise ValueError("retired_at must be set exactly when status is RETIRED")
        if self.retired_at is not None and self.retired_at <= self.installed_at:
            raise ValueError("retired_at must be after installed_at")
        return self


class OperatingState(StrEnum):
    """Machine/component operating state (L3-02). Not a health state."""

    RUNNING = "RUNNING"
    IDLE = "IDLE"
    STOPPED = "STOPPED"
    MAINTENANCE = "MAINTENANCE"
    FAULT = "FAULT"
    UNKNOWN = "UNKNOWN"


class MotionDirection(StrEnum):
    FORWARD = "FORWARD"
    REVERSE = "REVERSE"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


class AccelerationPhase(StrEnum):
    ACCELERATING = "ACCELERATING"
    CONSTANT = "CONSTANT"
    DECELERATING = "DECELERATING"
    STANDSTILL = "STANDSTILL"
    UNKNOWN = "UNKNOWN"


class OperatingRegime(ContractModel):
    """Observable operating conditions used for normalization and eligibility (L3-03)."""

    regime_id: str
    speed_band: str | None = None
    direction: MotionDirection = MotionDirection.UNKNOWN
    phase: AccelerationPhase = AccelerationPhase.UNKNOWN
    load_class: str | None = None
    recipe: str | None = None
    supported: bool = Field(description="False for unknown/unsupported regimes (scenario S17)")


class CycleKind(StrEnum):
    EXTEND = "EXTEND"
    RETRACT = "RETRACT"
    VACUUM_RELEASE = "VACUUM_RELEASE"
    MOTION_SEGMENT = "MOTION_SEGMENT"


class MovementCycle(ContractModel):
    cycle_id: str
    component_id: str
    lifecycle_id: str
    kind: CycleKind
    start: AwareDatetime
    end: AwareDatetime | None = None
    duration_s: float | None = Field(default=None, ge=0)
    complete: bool
    regime_id: str | None = None
    plausible: bool = Field(default=True, description="False: far from typical, kept out of statistics")
    direction: MotionDirection | None = Field(default=None, description="Motion segments only")
    signal_id: str | None = Field(default=None, description="Signal the cycle was derived from")
    is_simulated: bool


class StateSegment(ContractModel):
    """A stretch of time with one derived operating state and the evidence for it (L3-02)."""

    start: AwareDatetime
    end: AwareDatetime
    state: OperatingState
    evidence: list[str] = Field(default_factory=list, description="Signal ids or record ids used")
    reason: LocalizedText
    is_simulated: bool


class FeatureStats(ContractModel):
    """Robust level of one per-window feature, e.g. cruise speed of a speed signal."""

    feature_id: str = Field(description="'<signal_id>:<feature>', e.g. 'M01-BS1.torque:cruise'")
    median: float
    mad: float = Field(ge=0)
    count: int = Field(ge=0)


class KnownRegime(ContractModel):
    """A regime established from a reference period. Matching uses speed features only."""

    regime: OperatingRegime
    match_features: list[FeatureStats]
    reference: list[FeatureStats] = Field(description="Per-regime levels used for normalization (L4-03)")
    window_count: int = Field(ge=1)


class RegimeCatalog(ContractModel):
    catalog_id: str
    machine_id: str
    learned_from: TimeWindow
    tolerance: float = Field(gt=0, description="Relative tolerance on each speed feature")
    regimes: list[KnownRegime]
    is_simulated: bool


class RegimeStatus(StrEnum):
    KNOWN = "KNOWN"
    UNSUPPORTED = "UNSUPPORTED"  # running in conditions no known regime covers (S17)
    NOT_EVALUATED = "NOT_EVALUATED"  # not running, or no speed signal to characterize the regime


class FeatureValue(ContractModel):
    feature_id: str
    value: float
    normalized: float | None = Field(default=None, description="Condition-normalized residual (L4-03)")


class RegimeAssignment(ContractModel):
    """Regime of one observation window."""

    start: AwareDatetime
    end: AwareDatetime
    state: OperatingState
    status: RegimeStatus
    regime_id: str | None = None
    features: list[FeatureValue] = Field(default_factory=list)
    reason: LocalizedText


class CycleSummary(ContractModel):
    """Operations of one actuator signal in a period; incomplete ones never count as durations."""

    signal_id: str
    component_id: str
    kind: CycleKind
    window: TimeWindow
    operation_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    incomplete_count: int = Field(ge=0)
    implausible_count: int = Field(default=0, ge=0)
    timeout_s: float | None = None
    timeout_inferred: bool = False
    median_duration_s: float | None = Field(default=None, description="Completed, plausible operations only")
    sufficient: bool = Field(description="Enough completed operations for duration statistics")
    min_completed: int
    is_simulated: bool


class MachineOperations(ContractModel):
    machine_id: str
    window: TimeWindow
    states: list[StateSegment]
    regimes: list[RegimeAssignment]
    cycles: list[MovementCycle]
    cycle_summaries: list[CycleSummary]
    catalog_id: str | None = None
    not_evaluated: list[OperatingState] = Field(
        default_factory=list, description="States this source cannot evidence (e.g. FAULT)"
    )
    is_simulated: bool


class MaintenanceEventType(StrEnum):
    LUBRICATION = "LUBRICATION"
    INSPECTION = "INSPECTION"
    ADJUSTMENT = "ADJUSTMENT"
    PARTIAL_REPAIR = "PARTIAL_REPAIR"
    REPLACEMENT = "REPLACEMENT"


class MaintenanceEvent(ContractModel):
    """An intervention event (L3-05). Lubrication never resets aging (L3-08)."""

    event_id: str
    component_id: str
    lifecycle_id: str
    type: MaintenanceEventType
    performed_at: AwareDatetime
    performed_by: str
    notes: str = ""
    new_lifecycle_id: str | None = Field(default=None, description="Set only for REPLACEMENT")
    is_simulated: bool

    @model_validator(mode="after")
    def _replacement_has_new_lifecycle(self) -> MaintenanceEvent:
        is_replacement = self.type == MaintenanceEventType.REPLACEMENT
        if is_replacement != (self.new_lifecycle_id is not None):
            raise ValueError("new_lifecycle_id must be set exactly for REPLACEMENT events")
        return self


class MaintenanceWorkflowState(StrEnum):
    MAINTENANCE_EVENT = "MAINTENANCE_EVENT"
    STABILIZATION = "STABILIZATION"
    POST_MAINTENANCE_VALIDATION = "POST_MAINTENANCE_VALIDATION"
    NORMAL_MONITORING = "NORMAL_MONITORING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


_W = MaintenanceWorkflowState
WORKFLOW_TRANSITIONS: dict[MaintenanceWorkflowState, frozenset[MaintenanceWorkflowState]] = {
    _W.MAINTENANCE_EVENT: frozenset({_W.STABILIZATION}),
    _W.STABILIZATION: frozenset({_W.POST_MAINTENANCE_VALIDATION}),
    _W.POST_MAINTENANCE_VALIDATION: frozenset({_W.NORMAL_MONITORING, _W.REVIEW_REQUIRED}),
    _W.NORMAL_MONITORING: frozenset({_W.MAINTENANCE_EVENT}),
    _W.REVIEW_REQUIRED: frozenset({_W.NORMAL_MONITORING, _W.MAINTENANCE_EVENT}),
}


def can_transition(current: MaintenanceWorkflowState, target: MaintenanceWorkflowState) -> bool:
    """Workflow rule from L3-07. REVIEW_REQUIRED leaves only by human review or new maintenance."""
    return target in WORKFLOW_TRANSITIONS[current]


class LifecycleInstall(ContractModel):
    """First installation of a component (later lifecycles come only from REPLACEMENT events)."""

    installed_at: AwareDatetime
    comment: str = Field(default="", max_length=500)


class UsageRecord(ContractModel):
    """Operation of a lifecycle in (usage_counted_until, until], e.g. from derived RUNNING time."""

    until: AwareDatetime
    operating_hours: float = Field(ge=0)
    cycles: int = Field(default=0, ge=0)
    source: str = Field(default="", max_length=200, description="How the usage was derived")


class ComponentAging(ContractModel):
    """Age of the active lifecycle at a time. Only replacement starts a new count (L3-06, L3-08)."""

    component_id: str
    lifecycle_id: str
    installed_at: AwareDatetime
    at: AwareDatetime
    calendar_hours: float = Field(ge=0)
    operating_hours: float = Field(ge=0)
    cycles: int = Field(ge=0)
    maintenance_since_install: int = Field(ge=0)
    last_maintenance_at: AwareDatetime | None = None


class MaintenanceEventCreate(ContractModel):
    component_id: str
    type: MaintenanceEventType
    performed_at: AwareDatetime
    notes: str = Field(default="", max_length=2000)


class WorkflowTransition(ContractModel):
    from_state: MaintenanceWorkflowState | None
    to_state: MaintenanceWorkflowState
    at: AwareDatetime
    by: str
    comment: str = ""


class MaintenanceWorkflow(ContractModel):
    """Post-maintenance workflow of one maintenance event (L3-07)."""

    workflow_id: str
    component_id: str
    lifecycle_id: str
    event_id: str
    state: MaintenanceWorkflowState
    started_at: AwareDatetime
    updated_at: AwareDatetime
    superseded_by: str | None = Field(default=None, description="Workflow of a later event that replaced it")
    transitions: list[WorkflowTransition] = Field(default_factory=list)
    is_simulated: bool


class WorkflowTransitionRequest(ContractModel):
    target: MaintenanceWorkflowState
    comment: str = Field(default="", max_length=500)
    expected_state: MaintenanceWorkflowState | None = Field(
        default=None, description="Refuse if the workflow moved on since the caller looked"
    )


class MaintenanceRecordResult(ContractModel):
    event: MaintenanceEvent
    lifecycles: list[ComponentLifecycle] = Field(description="Lifecycles the event touched")
    workflow: MaintenanceWorkflow | None
    superseded: list[str] = Field(default_factory=list, description="Open workflows this event replaced")


class ImpactOutcome(StrEnum):
    """Effect of a maintenance event on regime-normalized behavior (L3-07)."""

    IMPROVED = "IMPROVED"
    PARTIAL = "PARTIAL"  # improved, but still well above the regime reference
    NO_CHANGE = "NO_CHANGE"
    DETERIORATED = "DETERIORATED"
    UNKNOWN = "UNKNOWN"  # not enough comparable data before or after


class ImpactConfig(ContractModel):
    pre_hours: float = Field(default=72.0, gt=0, description="Period before the event used for comparison")
    stabilization_hours: float = Field(default=4.0, ge=0, description="Excluded after the event (L3-07)")
    validation_hours: float = Field(default=36.0, gt=0, description="Period after stabilization compared")
    max_validation_hours: float = Field(
        default=120.0,
        gt=0,
        description="Validation waits this long for comparable data, then asks for review",
    )
    min_pre_windows: int = Field(default=3, ge=1, description="Per regime, before the event")
    min_post_windows: int = Field(default=3, ge=1, description="In total across compatible regimes, after")
    effect: float = Field(
        default=2.0, gt=0, description="Median change, in robust units, that counts as an effect"
    )
    elevated: float = Field(default=3.0, gt=0, description="Post level above which an improvement is partial")


class RegimeComparison(ContractModel):
    regime_id: str
    pre_windows: int
    post_windows: int
    pre_median: float
    post_median: float


class FeatureImpact(ContractModel):
    feature_id: str
    outcome: ImpactOutcome
    change: float | None = Field(description="Post minus pre, robust units, weighted by post windows")
    post_level: float | None = Field(description="Median post value against the regime reference")
    regimes: list[RegimeComparison]


class MaintenanceImpact(ContractModel):
    component_id: str
    event_time: AwareDatetime
    pre: TimeWindow
    post: TimeWindow
    catalog_id: str
    config: ImpactConfig
    outcome: ImpactOutcome
    features: list[FeatureImpact]
    reason: LocalizedText
    is_simulated: bool
