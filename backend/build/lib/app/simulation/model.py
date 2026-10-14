"""Physical signal models and component health-state evolution for the simulator.

These are deliberately simple, documented models for demonstrations and tests. They are not
calibrated to any real machine and must never be presented as real behavior (GEN-03).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from app.equipment.schemas import ComponentType, MaintenanceEventType
from app.simulation.config import (
    COMPONENT_PARAMETERS,
    ComponentSpec,
    MaintenanceSpec,
    Recipe,
    Shape,
    SimulationConfig,
)

# Motion profile as fractions of the recipe cycle period: accelerate, cruise, decelerate, dwell.
ACCEL_FRAC, CRUISE_FRAC, DECEL_FRAC = 0.15, 0.25, 0.15
MOVE_FRAC = ACCEL_FRAC + CRUISE_FRAC + DECEL_FRAC

# Ball-screw servo torque model (N*m): T = f*(TC*sign(v) + B*v) + J*alpha + load*sign(v)
COULOMB_NM, VISCOUS_NM_PER_RPM, INERTIA_KGM2 = 0.8, 0.0004, 0.002
VACUUM_RELEASE_MS, CYL_EXTEND_MS, CYL_RETRACT_MS = 80.0, 350.0, 300.0


def stable_int(text: str) -> int:
    """Seed component derived from text, stable across Python processes (unlike hash())."""
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")


def rng_for(seed: int, *keys: str | int) -> np.random.Generator:
    return np.random.default_rng([seed, *(k if isinstance(k, int) else stable_int(k) for k in keys)])


@dataclass(frozen=True)
class HealthState:
    """True (simulated) condition of the installed part at one moment."""

    lifecycle_id: str
    wear: float
    parameters: dict[str, float]
    spread: float  # manufacturing variation of this installed part

    def factors(self, ctype: ComponentType) -> dict[str, float]:
        p, base = self.parameters, 1.0 + self.wear + self.spread
        if ctype == ComponentType.BALL_SCREW:
            return {"friction_factor": base + p["friction"] + p["lubrication"]}
        if ctype == ComponentType.LINEAR_MOTOR:
            return {"ripple_fraction": max(0.0, 0.005 + 0.02 * self.wear + 0.1 * self.spread + p["ripple"])}
        if ctype == ComponentType.VACUUM_CUP:
            return {"release_factor": base + p["release"]}
        if ctype == ComponentType.PNEUMATIC_CYLINDER:
            return {"extend_factor": base + p["extend"], "retract_factor": base + p["retract"]}
        return {}


class HealthModel:
    """Evaluates component health over time from aging, effects, and maintenance in the config."""

    def __init__(self, cfg: SimulationConfig):
        self.cfg = cfg
        self.components = {c.component_id: c for m in cfg.machines for c in m.components}
        self.replacements: dict[str, list[float]] = {cid: [] for cid in self.components}
        for mt in sorted(cfg.maintenance, key=lambda m: m.at_h):
            if mt.type == MaintenanceEventType.REPLACEMENT:
                self.replacements[mt.component_id].append(mt.at_h)

    def _targets(self, target: str, comp: ComponentSpec) -> bool:
        return target == comp.component_id or (
            comp.drive_chain_id is not None and target == comp.drive_chain_id
        )

    def lifecycle_index(self, cid: str, t_h: float) -> int:
        return sum(1 for r in self.replacements[cid] if r <= t_h)

    @staticmethod
    def lifecycle_id(cid: str, index: int) -> str:
        return f"{cid}-LC{index + 1}"

    def epoch_start(self, cid: str, t_h: float) -> float:
        past = [r for r in self.replacements[cid] if r <= t_h]
        return past[-1] if past else 0.0

    def state(self, cid: str, t_h: float) -> HealthState:
        comp = self.components[cid]
        idx = self.lifecycle_index(cid, t_h)
        epoch = self.epoch_start(cid, t_h)
        wear = comp.initial_wear if idx == 0 else 0.0
        wear += (
            sum(a.rate_per_1000h for a in self.cfg.aging if self._targets(a.target, comp))
            * (t_h - epoch)
            / 1000
        )
        params = dict.fromkeys(COMPONENT_PARAMETERS[comp.type], 0.0)
        for e in self.cfg.effects:
            if not self._targets(e.target, comp) or e.parameter not in params:
                continue
            if e.start_h < epoch or t_h < e.start_h:  # replaced parts do not inherit faults
                continue
            if e.shape == Shape.STEP:
                params[e.parameter] += e.magnitude
            else:
                assert e.end_h is not None
                params[e.parameter] += e.magnitude * min(1.0, (t_h - e.start_h) / (e.end_h - e.start_h))
        for mt in self._maintenance_in_epoch(cid, epoch, t_h):
            wear += mt.wear_delta
            for k, v in mt.parameter_deltas.items():
                params[k] += v
        spread = float(rng_for(self.cfg.seed, "spread", self.lifecycle_id(cid, idx)).normal(0, 0.02))
        return HealthState(self.lifecycle_id(cid, idx), max(0.0, wear), params, spread)

    def _maintenance_in_epoch(self, cid: str, epoch: float, t_h: float) -> list[MaintenanceSpec]:
        return [
            mt
            for mt in self.cfg.maintenance
            if mt.component_id == cid
            and mt.type != MaintenanceEventType.REPLACEMENT
            and epoch <= mt.at_h <= t_h
        ]


# --- motion and signal models (tau = seconds since window start) ------------------------------


def motion_profile(
    tau: np.ndarray, period_s: float, v_max: float, phase_s: float
) -> tuple[np.ndarray, np.ndarray]:
    """Trapezoidal moves alternating direction each period. Returns (velocity, acceleration per s)."""
    t = tau + phase_s
    cycle = np.floor(t / period_s)
    u = (t - cycle * period_s) / period_s
    direction = np.where(cycle % 2 == 0, 1.0, -1.0)
    ta, tc, td = ACCEL_FRAC, CRUISE_FRAC, DECEL_FRAC
    accel = v_max / (ta * period_s)
    v = np.select(
        [u < ta, u < ta + tc, u < ta + tc + td],
        [accel * u * period_s, np.full_like(u, v_max), v_max - accel * (u - ta - tc) * period_s],
        default=0.0,
    )
    a = np.select([u < ta, u < ta + tc, u < ta + tc + td], [accel, 0.0, -accel], default=0.0)
    return direction * v, direction * a


def cruising(tau: np.ndarray, period_s: float, phase_s: float) -> np.ndarray:
    u = ((tau + phase_s) % period_s) / period_s
    return (u >= ACCEL_FRAC) & (u < ACCEL_FRAC + CRUISE_FRAC)


def servo_signals(
    tau_speed: np.ndarray,
    tau_torque: np.ndarray,
    recipe: Recipe,
    running: bool,
    friction_factor: float,
    phase_s: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Speed (rpm) and torque (N*m) for a ball-screw servo. Torque can be sampled at shifted times."""
    if not running:
        speed = rng.normal(0, 0.5, tau_speed.size)
        torque = 0.1 * recipe.load_nm + rng.normal(0, 0.05, tau_torque.size)
        return speed, torque
    v, _ = motion_profile(tau_speed, recipe.cycle_period_s, recipe.servo_speed_rpm, phase_s)
    speed = v + rng.normal(0, 2.0, v.size) * (v != 0) + rng.normal(0, 0.5, v.size) * (v == 0)
    vt, at = motion_profile(tau_torque, recipe.cycle_period_s, recipe.servo_speed_rpm, phase_s)
    moving = vt != 0
    sign = np.sign(vt)
    alpha = at * 2 * np.pi / 60
    torque = np.where(
        moving,
        friction_factor * (COULOMB_NM * sign + VISCOUS_NM_PER_RPM * vt)
        + INERTIA_KGM2 * alpha
        + recipe.load_nm * sign,
        0.1 * recipe.load_nm,
    )
    return speed, torque + rng.normal(0, 0.05, torque.size)


def linear_speed(
    tau: np.ndarray,
    recipe: Recipe,
    running: bool,
    ripple_fraction: float,
    phase_s: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Linear motor real-time speed (mm/s) with speed ripple while cruising."""
    if not running:
        return rng.normal(0, 0.2, tau.size)
    v, _ = motion_profile(tau, recipe.cycle_period_s, recipe.linear_speed_mm_s, phase_s)
    ripple = ripple_fraction * recipe.linear_speed_mm_s
    osc = np.sin(2 * np.pi * 7.3 * tau + rng.uniform(0, 2 * np.pi)) + 0.5 * rng.normal(0, 1, tau.size)
    noise = rng.normal(0, 0.2, tau.size)
    return v + np.where(cruising(tau, recipe.cycle_period_s, phase_s), ripple * osc, 0.0) + noise


def cycle_starts(window_s: float, period_s: float, phase_s: float) -> np.ndarray:
    first = (period_s - phase_s) % period_s
    return np.arange(first, window_s - period_s * MOVE_FRAC, period_s)
