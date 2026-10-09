"""Deterministic generation of raw IoT-style telemetry, normalized signals, topology, and ground truth."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import timedelta

import numpy as np

from app.core.schemas import LocalizedText
from app.equipment.schemas import (
    TEMPLATE_ONLY_TYPES,
    ComponentInstance,
    ComponentLifecycle,
    ComponentType,
    LifecycleStatus,
    Machine,
    MaintenanceEvent,
    MaintenanceEventType,
    OperatingState,
)
from app.signals.schemas import PhysicalQuantity, SignalDefinition, SignalMapping, UnitConversion
from app.simulation.config import ComponentSpec, DataFaultKind, MachineSpec, SimulationConfig
from app.simulation.model import (
    CYL_EXTEND_MS,
    CYL_RETRACT_MS,
    VACUUM_RELEASE_MS,
    HealthModel,
    cycle_starts,
    linear_speed,
    rng_for,
    servo_signals,
)

GENERATOR_VERSION = "sim-1.0.0"
DATA_SOURCE_ID = "simulated"


@dataclass(frozen=True)
class SignalSpec:
    key_suffix: str
    signal_suffix: str
    name: LocalizedText
    quantity: PhysicalQuantity
    raw_unit: str
    unit: str
    scale: float  # normalized = raw * scale
    event_based: bool


def signal_specs(comp: ComponentSpec) -> list[SignalSpec]:
    L = LocalizedText
    if comp.type == ComponentType.BALL_SCREW:
        return [
            SignalSpec(
                "SPD",
                "speed",
                L(zh="伺服转速", en="Servo speed"),
                PhysicalQuantity.SPEED,
                "rpm",
                "rpm",
                1.0,
                False,
            ),
            SignalSpec(
                "TRQ",
                "torque",
                L(zh="伺服转矩", en="Servo torque"),
                PhysicalQuantity.TORQUE,
                "%rated",
                "N*m",
                comp.rated_torque_nm / 100,
                False,
            ),
        ]
    if comp.type == ComponentType.LINEAR_MOTOR:
        return [
            SignalSpec(
                "SPD",
                "speed",
                L(zh="直线电机速度", en="Linear motor speed"),
                PhysicalQuantity.SPEED,
                "mm/s",
                "m/s",
                0.001,
                False,
            )
        ]
    if comp.type == ComponentType.VACUUM_CUP:
        return [
            SignalSpec(
                "REL",
                "release_time",
                L(zh="真空释放时间", en="Vacuum release time"),
                PhysicalQuantity.DURATION,
                "ms",
                "s",
                0.001,
                True,
            )
        ]
    if comp.type == ComponentType.PNEUMATIC_CYLINDER:
        return [
            SignalSpec(
                "EXT",
                "extend_time",
                L(zh="气缸伸出时间", en="Cylinder extension time"),
                PhysicalQuantity.DURATION,
                "ms",
                "s",
                0.001,
                True,
            ),
            SignalSpec(
                "RET",
                "retract_time",
                L(zh="气缸缩回时间", en="Cylinder retraction time"),
                PhysicalQuantity.DURATION,
                "ms",
                "s",
                0.001,
                True,
            ),
        ]
    return []  # cam/gear: template only, no telemetry yet


def key_name(comp: ComponentSpec, spec: SignalSpec) -> str:
    return f"{comp.component_id.replace('-', '_').upper()}_{spec.key_suffix}"


def signal_id(comp: ComponentSpec, spec: SignalSpec) -> str:
    return f"{comp.component_id}.{spec.signal_suffix}"


@dataclass
class Window:
    machine_id: str
    index: int
    start_h: float
    end_h: float
    state: OperatingState
    recipe_id: str


@dataclass
class Series:
    """Raw samples for one key: seconds since simulation start and raw values."""

    device_id: str
    key: str
    t: list[np.ndarray] = field(default_factory=list)
    v: list[np.ndarray] = field(default_factory=list)

    def arrays(self) -> tuple[np.ndarray, np.ndarray]:
        if not self.t:
            return np.empty(0), np.empty(0)
        return np.concatenate(self.t), np.concatenate(self.v)


@dataclass
class SimulationResult:
    config: SimulationConfig
    machines: list[Machine]
    components: list[ComponentInstance]
    lifecycles: list[ComponentLifecycle]
    signals: list[SignalDefinition]
    mappings: list[SignalMapping]
    maintenance_events: list[MaintenanceEvent]
    windows: list[Window]
    component_truth: list[dict[str, object]]
    raw: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]]  # (device, key) -> (seconds, raw values)
    fault_log: list[dict[str, object]]
    incomplete_log: list[dict[str, object]]


def _windows(cfg: SimulationConfig, m: MachineSpec) -> list[Window]:
    obs = cfg.observation
    spacing_h = 24 / obs.windows_per_day
    win_h = obs.window_minutes / 60
    offset_h = spacing_h / 2 - win_h / 2
    rng = rng_for(cfg.seed, "windows", m.machine_id)
    maint = [
        (mt.at_h, mt.at_h + mt.duration_h)
        for mt in cfg.maintenance
        if mt.component_id in {c.component_id for c in m.components}
    ]
    out: list[Window] = []
    for i in range(math.ceil(cfg.duration_hours / spacing_h)):
        start = i * spacing_h + offset_h
        end = start + win_h
        if end > cfg.duration_hours:
            break
        draw, recipe_draw = rng.random(), rng.integers(0, len(m.recipes))
        recipe = m.recipes[recipe_draw]
        for hour, rid in m.recipe_schedule:
            if hour <= start:
                recipe = rid
        if any(a < end and start < b for a, b in maint):
            state = OperatingState.MAINTENANCE
        elif draw < obs.stopped_fraction:
            state = OperatingState.STOPPED
        elif draw < obs.stopped_fraction + obs.idle_fraction:
            state = OperatingState.IDLE
        else:
            state = OperatingState.RUNNING
        out.append(Window(m.machine_id, i, start, end, state, recipe))
    return out


def _fault_offset(cfg: SimulationConfig, device: str, key: str, t_s: np.ndarray) -> np.ndarray:
    """Per-sample SYNC_OFFSET (seconds) by which the value lags its timestamp."""
    lag = np.zeros_like(t_s)
    for f in cfg.data_faults:
        if f.kind == DataFaultKind.SYNC_OFFSET and f.device_id == device and key in f.key_names:
            lag += np.where((t_s >= f.start_h * 3600) & (t_s < f.end_h * 3600), f.offset_s, 0.0)
    return lag


def generate(cfg: SimulationConfig) -> SimulationResult:
    health = HealthModel(cfg)
    recipes = {r.recipe_id: r for r in cfg.recipes}
    obs = cfg.observation
    win_s = obs.window_minutes * 60

    machines, components, signals, mappings = [], [], [], []
    windows: list[Window] = []
    series: dict[tuple[str, str], Series] = {}
    truth: list[dict[str, object]] = []
    incomplete_log: list[dict[str, object]] = []
    running_hours: dict[str, float] = {}

    for m in cfg.machines:
        machines.append(Machine(machine_id=m.machine_id, name=m.name, is_simulated=True))
        for c in m.components:
            specs = signal_specs(c)
            components.append(
                ComponentInstance(
                    component_id=c.component_id,
                    machine_id=m.machine_id,
                    type=c.type,
                    name=c.name,
                    drive_chain_id=c.drive_chain_id,
                    signal_ids=[signal_id(c, s) for s in specs],
                )
            )
            for s in specs:
                sid, key = signal_id(c, s), key_name(c, s)
                signals.append(
                    SignalDefinition(
                        signal_id=sid,
                        name=s.name,
                        quantity=s.quantity,
                        unit=s.unit,
                        expected_sampling_s=None if s.event_based else obs.servo_sample_s,
                    )
                )
                mappings.append(
                    SignalMapping(
                        signal_id=sid,
                        data_source_id=DATA_SOURCE_ID,
                        template_id="sim-telemetry-by-key",
                        device_id=m.device_id,
                        key_name=key,
                        time_field="ts",
                        value_field="value_double",
                        conversion=UnitConversion(source_unit=s.raw_unit, target_unit=s.unit, scale=s.scale),
                        component_id=c.component_id,
                    )
                )
                series[(m.device_id, key)] = Series(m.device_id, key)

        m_windows = _windows(cfg, m)
        windows.extend(m_windows)
        for w in m_windows:
            recipe = recipes[w.recipe_id]
            active = w.state in (OperatingState.RUNNING, OperatingState.IDLE)
            running = w.state == OperatingState.RUNNING
            t0 = w.start_h * 3600
            for c in m.components:
                hs = health.state(c.component_id, w.start_h)
                factors = hs.factors(c.type)
                if c.type not in TEMPLATE_ONLY_TYPES:
                    truth.append(
                        {
                            "window_start_h": w.start_h,
                            "machine_id": m.machine_id,
                            "component_id": c.component_id,
                            "lifecycle_id": hs.lifecycle_id,
                            "state": w.state.value,
                            "recipe_id": w.recipe_id,
                            "wear": hs.wear,
                            **factors,
                        }
                    )
                if running:
                    running_hours[hs.lifecycle_id] = running_hours.get(hs.lifecycle_id, 0.0) + win_s / 3600
                if not active or c.type in TEMPLATE_ONLY_TYPES:
                    continue
                rng = rng_for(cfg.seed, "signal", c.component_id, w.index)
                phase = float(rng.uniform(0, recipe.cycle_period_s))
                specs = signal_specs(c)
                keys = [key_name(c, s) for s in specs]
                if c.type == ComponentType.BALL_SCREW:
                    tau = np.arange(0, win_s, obs.servo_sample_s)
                    lag_spd = _fault_offset(cfg, m.device_id, keys[0], t0 + tau)
                    lag_trq = _fault_offset(cfg, m.device_id, keys[1], t0 + tau)
                    spd, trq = servo_signals(
                        tau - lag_spd, tau - lag_trq, recipe, running, factors["friction_factor"], phase, rng
                    )
                    _append(series, m.device_id, keys[0], t0 + tau, spd)
                    _append(series, m.device_id, keys[1], t0 + tau, trq / c.rated_torque_nm * 100)
                elif c.type == ComponentType.LINEAR_MOTOR:
                    tau = np.arange(0, win_s, obs.linear_sample_s)
                    lag = _fault_offset(cfg, m.device_id, keys[0], t0 + tau)
                    v = linear_speed(tau - lag, recipe, running, factors["ripple_fraction"], phase, rng)
                    _append(series, m.device_id, keys[0], t0 + tau, v)
                elif running:  # event-based actuators report one value per completed operation
                    starts = cycle_starts(win_s, recipe.cycle_period_s, phase)
                    n = starts.size
                    if c.type == ComponentType.VACUUM_CUP:
                        vals = [
                            VACUUM_RELEASE_MS
                            * factors["release_factor"]
                            * recipe.part_factor
                            * np.exp(rng.normal(0, 0.04, n))
                        ]
                        stamps = [starts + 0.2 * recipe.cycle_period_s]
                    else:
                        vals = [
                            CYL_EXTEND_MS
                            * factors["extend_factor"]
                            * recipe.pressure_factor
                            * np.exp(rng.normal(0, 0.03, n)),
                            CYL_RETRACT_MS
                            * factors["retract_factor"]
                            * recipe.pressure_factor
                            * np.exp(rng.normal(0, 0.03, n)),
                        ]
                        stamps = [starts + 0.1 * recipe.cycle_period_s, starts + 0.6 * recipe.cycle_period_s]
                    vals = _incomplete(cfg, c.component_id, w, t0, stamps, vals, rng, incomplete_log)
                    for key, st, vv in zip(keys, stamps, vals, strict=True):
                        _append(series, m.device_id, key, t0 + st, vv)

    raw, fault_log = _apply_faults(cfg, series)
    lifecycles = _lifecycles(cfg, health, running_hours)
    events = _maintenance_events(cfg, health)
    return SimulationResult(
        cfg,
        machines,
        components,
        lifecycles,
        signals,
        mappings,
        events,
        windows,
        truth,
        raw,
        fault_log,
        incomplete_log,
    )


def _append(
    series: dict[tuple[str, str], Series], device: str, key: str, t: np.ndarray, v: np.ndarray
) -> None:
    series[(device, key)].t.append(np.asarray(t, dtype=float))
    series[(device, key)].v.append(np.asarray(v, dtype=float))


def _incomplete(cfg, cid, w, t0, stamps, vals, rng, log):
    for spec in cfg.incomplete_ops:
        if spec.component_id != cid or not (spec.start_h <= w.start_h < spec.end_h):
            continue
        n = stamps[0].size
        hit = rng.random(n) < spec.rate
        which = rng.integers(0, len(vals), n)  # for cylinders: extension or retraction failed to complete
        for j, (st, vv) in enumerate(zip(stamps, vals, strict=True)):
            mask = hit & (which == j)
            vals[j] = np.where(mask, spec.timeout_ms, vv)
            for s in st[mask]:
                log.append({"component_id": cid, "operation": j, "t_s": round(float(t0 + s), 3)})
    return vals


def _apply_faults(cfg: SimulationConfig, series: dict[tuple[str, str], Series]):
    raw: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
    log: list[dict[str, object]] = []
    for (device, key), s in sorted(series.items()):
        t, v = s.arrays()
        for i, f in enumerate(cfg.data_faults):
            if f.device_id != device or key not in f.key_names or f.kind == DataFaultKind.SYNC_OFFSET:
                continue
            rng = rng_for(cfg.seed, "fault", i, key)
            inside = (t >= f.start_h * 3600) & (t < f.end_h * 3600)
            before = t.size
            if f.kind == DataFaultKind.INTERRUPTION:
                t, v = t[~inside], v[~inside]
            elif f.kind == DataFaultKind.MISSING:
                keep = ~(inside & (rng.random(t.size) < f.rate))
                t, v = t[keep], v[keep]
            elif f.kind == DataFaultKind.DUPLICATE:
                rep = np.where(inside & (rng.random(t.size) < f.rate), 2, 1)
                t, v = np.repeat(t, rep), np.repeat(v, rep)
            elif f.kind == DataFaultKind.JITTER:
                t = np.where(inside, t + rng.normal(0, f.jitter_s, t.size), t)
            elif f.kind == DataFaultKind.BIAS:
                v = np.where(inside, v + f.bias, v)
            elif f.kind == DataFaultKind.UNIT_SCALE:
                v = np.where(inside, v * f.scale, v)
            elif f.kind == DataFaultKind.OUT_OF_ORDER:
                order = np.arange(t.size)
                swap = np.flatnonzero(inside[:-1] & inside[1:] & (rng.random(max(t.size - 1, 0)) < f.rate))
                for j in swap:
                    order[j], order[j + 1] = order[j + 1], order[j]
                t, v = t[order], v[order]
            log.append(
                {
                    "fault_index": i,
                    "kind": f.kind.value,
                    "device_id": device,
                    "key_name": key,
                    "rows_in_interval": int(inside.sum()),
                    "rows_before": before,
                    "rows_after": int(t.size),
                }
            )
        raw[(device, key)] = (t, v)
    for i, f in enumerate(cfg.data_faults):
        if f.kind == DataFaultKind.SYNC_OFFSET:
            log.append(
                {
                    "fault_index": i,
                    "kind": f.kind.value,
                    "device_id": f.device_id,
                    "key_names": f.key_names,
                    "offset_s": f.offset_s,
                }
            )
    return raw, log


def _lifecycles(cfg: SimulationConfig, health: HealthModel, running_hours: dict[str, float]):
    out = []
    for m in cfg.machines:
        for c in m.components:
            times = [0.0, *health.replacements[c.component_id]]
            for idx, start_h in enumerate(times):
                lid = health.lifecycle_id(c.component_id, idx)
                end_h = times[idx + 1] if idx + 1 < len(times) else None
                out.append(
                    ComponentLifecycle(
                        lifecycle_id=lid,
                        component_id=c.component_id,
                        installed_at=cfg.start + timedelta(hours=start_h),
                        retired_at=None if end_h is None else cfg.start + timedelta(hours=end_h),
                        predecessor_lifecycle_id=health.lifecycle_id(c.component_id, idx - 1)
                        if idx
                        else None,
                        status=LifecycleStatus.ACTIVE if end_h is None else LifecycleStatus.RETIRED,
                        accumulated_operating_hours=round(running_hours.get(lid, 0.0), 4),
                    )
                )
    return out


def _maintenance_events(cfg: SimulationConfig, health: HealthModel) -> list[MaintenanceEvent]:
    out = []
    for i, mt in enumerate(sorted(cfg.maintenance, key=lambda x: (x.at_h, x.component_id))):
        before = health.lifecycle_index(mt.component_id, mt.at_h - 1e-9)
        replacement = mt.type == MaintenanceEventType.REPLACEMENT
        out.append(
            MaintenanceEvent(
                event_id=f"SIM-ME-{i + 1:04d}",
                component_id=mt.component_id,
                lifecycle_id=health.lifecycle_id(mt.component_id, before),
                type=mt.type,
                performed_at=cfg.start + timedelta(hours=mt.at_h),
                performed_by=mt.performed_by,
                notes="simulated maintenance event",
                new_lifecycle_id=health.lifecycle_id(mt.component_id, before + 1) if replacement else None,
                is_simulated=True,
            )
        )
    return out
