"""L3 contracts: topology, operating state, regimes, cycles, maintenance, lifecycles."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field, model_validator

from app.core.schemas import ContractModel, LocalizedText


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


class ComponentInstance(ContractModel):
    component_id: str
    machine_id: str
    type: ComponentType
    name: LocalizedText
    drive_chain_id: str | None = Field(
        default=None, description="Components sharing a drive chain (scenario S19) share this id"
    )
    signal_ids: list[str] = Field(default_factory=list)


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
