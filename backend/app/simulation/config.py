"""Simulation configuration (SIM-02). Every run is fully determined by this config and its seed."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from app.core.schemas import ContractModel, LocalizedText
from app.equipment.schemas import ComponentType, MaintenanceEventType

# Adjustable health parameters per component type. Each starts at 0 for a new component and adds to a
# dimensionless degradation factor (see model.py). ``wear`` is shared and driven by AgingSpec.
COMPONENT_PARAMETERS: dict[ComponentType, tuple[str, ...]] = {
    ComponentType.BALL_SCREW: ("friction", "lubrication"),
    ComponentType.LINEAR_MOTOR: ("ripple",),
    ComponentType.VACUUM_CUP: ("release",),
    ComponentType.PNEUMATIC_CYLINDER: ("extend", "retract"),
    ComponentType.CAM: (),
    ComponentType.GEAR: (),
}


class Recipe(ContractModel):
    """Observable operating condition set. Downstream code must infer regimes; the recipe is ground truth."""

    recipe_id: str
    servo_speed_rpm: float = Field(gt=0)
    load_nm: float = Field(ge=0)
    linear_speed_mm_s: float = Field(gt=0)
    cycle_period_s: float = Field(gt=1)
    pressure_factor: float = Field(default=1.0, gt=0, description="Pneumatic supply effect on durations")
    part_factor: float = Field(default=1.0, gt=0, description="Workpiece effect on vacuum release")


class ComponentSpec(ContractModel):
    component_id: str
    type: ComponentType
    name: LocalizedText
    drive_chain_id: str | None = None
    rated_torque_nm: float = Field(default=10.0, gt=0)
    initial_wear: float = Field(default=0.0, ge=0)


class MachineSpec(ContractModel):
    machine_id: str
    name: LocalizedText
    device_id: str = Field(pattern=r"^SIM-", description="Simulated device ids always start with SIM-")
    components: list[ComponentSpec] = Field(min_length=1)
    recipes: list[str] = Field(min_length=1, description="Recipe ids this machine runs, chosen per window")
    recipe_schedule: list[tuple[float, str]] = Field(
        default_factory=list, description="(start_hour, recipe_id) overrides, sorted by hour"
    )


class AgingSpec(ContractModel):
    """Irreversible wear accumulation for the installed part: ``wear += rate * hours / 1000``."""

    target: str = Field(description="component_id or drive_chain_id")
    rate_per_1000h: float


class Shape(StrEnum):
    STEP = "STEP"
    LINEAR = "LINEAR"


class ParameterEffect(ContractModel):
    """Fault or condition change on one health parameter of the installed part.

    LINEAR ramps from 0 at ``start_h`` to ``magnitude`` at ``end_h`` and holds; STEP applies
    ``magnitude`` from ``start_h``. A replacement cancels effects that started before it.
    """

    target: str = Field(description="component_id or drive_chain_id")
    parameter: str
    shape: Shape
    start_h: float = Field(ge=0)
    end_h: float | None = None
    magnitude: float

    @model_validator(mode="after")
    def _ramp_end(self) -> ParameterEffect:
        if self.shape == Shape.LINEAR and (self.end_h is None or self.end_h <= self.start_h):
            raise ValueError("LINEAR effects need end_h > start_h")
        return self


class MaintenanceSpec(ContractModel):
    component_id: str
    at_h: float = Field(ge=0)
    type: MaintenanceEventType
    parameter_deltas: dict[str, float] = Field(
        default_factory=dict, description="Added to parameters afterwards"
    )
    wear_delta: float = Field(
        default=0.0, description="Partial repair may reduce wear; lubrication never does"
    )
    duration_h: float = Field(default=0.5, gt=0)
    performed_by: str = "sim-technician"

    @model_validator(mode="after")
    def _lubrication_keeps_aging(self) -> MaintenanceSpec:
        if self.type == MaintenanceEventType.LUBRICATION and self.wear_delta != 0:
            raise ValueError("lubrication must not change accumulated wear (L3-08)")
        return self


class DataFaultKind(StrEnum):
    MISSING = "MISSING"  # drop rows with probability rate
    DUPLICATE = "DUPLICATE"  # repeat rows with probability rate
    JITTER = "JITTER"  # add N(0, jitter_s) to timestamps
    OUT_OF_ORDER = "OUT_OF_ORDER"  # swap adjacent rows in output order with probability rate
    SYNC_OFFSET = "SYNC_OFFSET"  # values lag their timestamps by offset_s (speed/torque desync)
    BIAS = "BIAS"  # add bias in raw units
    UNIT_SCALE = "UNIT_SCALE"  # multiply raw values by scale (unit mismatch)
    INTERRUPTION = "INTERRUPTION"  # no rows at all in [start_h, end_h)


class DataFaultSpec(ContractModel):
    kind: DataFaultKind
    key_names: list[str] = Field(min_length=1, description="Raw key names affected")
    device_id: str
    start_h: float = Field(ge=0)
    end_h: float
    rate: float = Field(default=0.0, ge=0, le=1)
    jitter_s: float = Field(default=0.0, ge=0)
    offset_s: float = 0.0
    bias: float = 0.0
    scale: float = 1.0


class IncompleteOpsSpec(ContractModel):
    """Actuator operations that never complete; the controller reports its timeout value instead."""

    component_id: str
    start_h: float = Field(ge=0)
    end_h: float
    rate: float = Field(gt=0, le=1)
    timeout_ms: float = Field(default=2000, gt=0)


class ObservationSpec(ContractModel):
    windows_per_day: int = Field(default=4, ge=1, le=96)
    window_minutes: float = Field(default=5, gt=0, le=60)
    servo_sample_s: float = Field(default=1.0, gt=0)
    linear_sample_s: float = Field(default=1.0, gt=0)
    idle_fraction: float = Field(default=0.1, ge=0, le=1)
    stopped_fraction: float = Field(default=0.05, ge=0, le=1)


class SimulationConfig(ContractModel):
    dataset_id: str = Field(pattern=r"^[a-z0-9_]+$")
    description: str
    seed: int = Field(ge=0)
    start: AwareDatetime
    duration_hours: float = Field(gt=0, le=24 * 400)
    observation: ObservationSpec = ObservationSpec()
    recipes: list[Recipe] = Field(min_length=1)
    machines: list[MachineSpec] = Field(min_length=1)
    aging: list[AgingSpec] = Field(default_factory=list)
    effects: list[ParameterEffect] = Field(default_factory=list)
    maintenance: list[MaintenanceSpec] = Field(default_factory=list)
    data_faults: list[DataFaultSpec] = Field(default_factory=list)
    incomplete_ops: list[IncompleteOpsSpec] = Field(default_factory=list)
    timestamp_format: Literal["iso_utc"] = "iso_utc"

    @model_validator(mode="after")
    def _references(self) -> SimulationConfig:
        recipes = {r.recipe_id for r in self.recipes}
        components = {c.component_id: c for m in self.machines for c in m.components}
        chains = {c.drive_chain_id for c in components.values() if c.drive_chain_id}
        devices = {m.device_id for m in self.machines}
        if len(components) != sum(len(m.components) for m in self.machines):
            raise ValueError("component ids must be unique")
        for m in self.machines:
            for r in [*m.recipes, *(r for _, r in m.recipe_schedule)]:
                if r not in recipes:
                    raise ValueError(f"unknown recipe {r}")
        for e in self.effects:
            targets = (
                [components[e.target]]
                if e.target in components
                else [c for c in components.values() if c.drive_chain_id == e.target]
            )
            if not targets:
                raise ValueError(f"unknown effect target {e.target}")
            for c in targets:
                if e.parameter not in COMPONENT_PARAMETERS[c.type]:
                    raise ValueError(f"{c.type} has no parameter {e.parameter}")
        for a in self.aging:
            if a.target not in components and a.target not in chains:
                raise ValueError(f"unknown aging target {a.target}")
        for mt in self.maintenance:
            if mt.component_id not in components:
                raise ValueError(f"unknown maintenance component {mt.component_id}")
            bad = set(mt.parameter_deltas) - set(COMPONENT_PARAMETERS[components[mt.component_id].type])
            if bad:
                raise ValueError(f"unknown parameters {bad} for {mt.component_id}")
        for f in self.data_faults:
            if f.device_id not in devices:
                raise ValueError(f"unknown fault device {f.device_id}")
        for op in self.incomplete_ops:
            c = components.get(op.component_id)
            if c is None or c.type not in (ComponentType.PNEUMATIC_CYLINDER, ComponentType.VACUUM_CUP):
                raise ValueError(f"incomplete ops need an actuator component, got {op.component_id}")
        return self
