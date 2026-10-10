"""Demo fleet fixture for the frontend (T007/T008): one simulated machine per selected scenario.

Health shown in the demo is the scenario's *expected* response from its Golden Case, not a computed
result. The monitoring engine arrives in T017-T024. The fixture says so in ``health_basis``.
"""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import fmean, pstdev

from app.core.schemas import LocalizedText
from app.decision.schemas import HealthState
from app.simulation.golden import Expectation, load_golden_cases
from app.simulation.writer import read_text

# (machine_id, scenario_id, snapshot day, machine name zh, en)
FLEET = [
    ("A01", "S01", 10, "1号装配机", "Assembly machine 1"),
    ("A02", "S04", 28, "2号装配机", "Assembly machine 2"),
    ("A03", "S03", 100, "3号装配机", "Assembly machine 3"),
    ("A04", "S07", 18, "4号压装机", "Press-fit machine 4"),
    ("A05", "S12", 22, "5号装配机", "Assembly machine 5"),
    ("A06", "S19", 18, "6号龙门机", "Gantry machine 6"),
    ("A07", "S20", 4, "7号装配机", "Assembly machine 7"),
    ("A08", "S05", 10, "8号传送机", "Transfer machine 8"),
]
TEMPLATE_COMPONENTS = [  # added to A01 to show extensible templates without telemetry
    ("CAM1", "CAM", "分度凸轮", "Indexing cam"),
    ("GR1", "GEAR", "减速齿轮", "Reduction gear"),
]
SEVERITY = [HealthState.NORMAL, HealthState.WATCH, HealthState.WARNING, HealthState.CRITICAL]
HEALTH_BASIS = LocalizedText(
    zh="演示：健康状态取自模拟场景的预期结果（Golden Case），并非监测引擎计算结果。",
    en="Demo: health is the simulated scenario's expected result (Golden Case), "
    "not computed by a monitoring engine.",
)


def _rows(scen_dir: Path, name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(read_text(scen_dir / name))))


def _deviation(truth_row: dict[str, str]) -> float:
    """Degradation magnitude from ground truth: factor above 1, or ripple fraction scaled."""
    vals = []
    for col in ("friction_factor", "release_factor", "extend_factor", "retract_factor"):
        if truth_row.get(col):
            vals.append(float(truth_row[col]) - 1.0)
    if truth_row.get("ripple_fraction"):
        vals.append(float(truth_row["ripple_fraction"]) * 10)
    return max(vals) if vals else 0.0


def _display_state(exp: Expectation, deviation: float) -> HealthState:
    allowed = exp.allowed_health
    if exp.must_abstain or allowed == [HealthState.UNKNOWN]:
        return HealthState.UNKNOWN
    target = 0 if deviation < 0.08 else 1 if deviation < 0.2 else 2 if deviation < 0.45 else 3
    ranked = [s for s in SEVERITY if s in allowed]
    if not ranked:
        return HealthState.UNKNOWN
    return min(ranked, key=lambda s: (abs(SEVERITY.index(s) - target), -SEVERITY.index(s)))


def _trend(
    norm: list[dict[str, str]], signals: list[str], cutoff: str, windows_in_regime: set[str]
) -> dict[str, list[list[object]]]:
    """Per-window aggregates up to the snapshot within one regime, used as a history sparkline.

    Restricting to one regime keeps regime changes from masquerading as trends.
    """
    by_signal: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for r in norm:
        in_regime = r["ts"][:15] in windows_in_regime
        if r["signal_id"] in signals and r["ts"] <= cutoff and r["value"] and in_regime:
            by_signal[r["signal_id"]].append((r["ts"], float(r["value"])))
    out: dict[str, list[list[object]]] = {}
    for sid, samples in by_signal.items():
        windows: dict[str, list[float]] = defaultdict(list)
        for ts, v in samples:
            windows[ts[:15]].append(v)  # same 10-minute bucket = same observation window
        series = []
        for key, vals in sorted(windows.items()):
            if sid.endswith(".torque"):
                moving = [abs(v) for v in vals if abs(v) > 0.5]
                agg = fmean(moving) if len(moving) > 3 else None
            elif sid.endswith(".speed") and "LM" in sid:
                peak = max(abs(v) for v in vals)
                cruise = [abs(v) for v in vals if peak > 0.05 and abs(v) > 0.9 * peak]
                agg = pstdev(cruise) / peak * 100 if len(cruise) > 3 else None
            elif sid.endswith(".speed"):
                continue
            else:
                valid = [v for v in vals if v < 1.5]  # timeout values are not durations
                agg = fmean(valid) if valid else None
            if agg is not None:
                series.append([key + "0:00Z", round(agg, 5)])
        if series:
            out[sid] = series
    return out


TREND_REGIME = "R-A"  # sparkline history uses windows of this regime only
TREND_UNITS = {"torque": "N*m", "speed": "%", "release_time": "s", "extend_time": "s", "retract_time": "s"}


def build_fleet(data_dir: Path) -> dict[str, object]:
    cases = load_golden_cases(data_dir)
    machines = []
    for machine_id, sid, day, zh, en in FLEET:
        (scen_dir,) = (data_dir / "scenarios").glob(f"{sid}_*")
        meta = json.loads((scen_dir / "scenario.json").read_text(encoding="utf-8"))
        topo = json.loads((scen_dir / "topology.json").read_text(encoding="utf-8"))
        cfg = json.loads((scen_dir / "config.json").read_text(encoding="utf-8"))
        start = datetime.fromisoformat(cfg["start"].replace("Z", "+00:00"))
        snapshot = start + timedelta(days=day)
        cutoff = snapshot.strftime("%Y-%m-%dT%H:%M:%S")
        snapshot_iso = snapshot.isoformat().replace("+00:00", "Z")
        truth = _rows(scen_dir, "truth_components.csv")
        norm = _rows(scen_dir, "normalized.csv")
        events = json.loads((scen_dir / "maintenance_events.json").read_text(encoding="utf-8"))
        regime_windows = {
            w["window_start"][:15]
            for w in _rows(scen_dir, "truth_windows.csv")
            if w["recipe_id"] == TREND_REGIME
        }
        components = []
        for comp in topo["components"]:
            cid = comp["component_id"]
            short = cid.split("-", 1)[1]
            case = next((c for c in cases if c.scenario_id == sid and c.component_id == cid), None)
            exp = None
            if case:
                exp = next((e for e in case.expectations if e.start_h <= day * 24 < e.end_h), None)
                if exp is None:  # between expectation intervals: use the latest one already started
                    started = [e for e in case.expectations if e.start_h <= day * 24]
                    exp = started[-1] if started else case.expectations[0]
            rows = [r for r in truth if r["component_id"] == cid and r["window_start"] <= cutoff]
            last = rows[-1] if rows else None
            state = _display_state(exp, _deviation(last)) if exp and last else HealthState.NORMAL
            reason = exp.note if exp else LocalizedText(zh="无异常证据", en="No abnormal evidence")
            lifecycles = [lc for lc in topo["lifecycles"] if lc["component_id"] == cid]
            components.append(
                {
                    "component_id": f"{machine_id}-{short}",
                    "source_component_id": cid,
                    "type": comp["type"],
                    "name": comp["name"],
                    "drive_chain_id": f"{machine_id}-DC1" if comp.get("drive_chain_id") else None,
                    "health": state.value,
                    "reason": reason.model_dump(),
                    "lifecycle_id": last["lifecycle_id"] if last else lifecycles[0]["lifecycle_id"],
                    "lifecycles": lifecycles,
                    "maintenance": [
                        e for e in events if e["component_id"] == cid and e["performed_at"] <= snapshot_iso
                    ],
                    "signals": [s for s in topo["signals"] if s["signal_id"] in comp["signal_ids"]],
                    "trend_regime": TREND_REGIME,
                    "trend": [
                        {"signal_id": k, "unit": TREND_UNITS[k.split(".")[-1]], "points": v}
                        for k, v in _trend(norm, comp["signal_ids"], cutoff, regime_windows).items()
                    ],
                }
            )
        if machine_id == "A01":
            for short, ctype, czh, cen in TEMPLATE_COMPONENTS:
                components.append(
                    {
                        "component_id": f"{machine_id}-{short}",
                        "source_component_id": None,
                        "type": ctype,
                        "name": {"zh": czh, "en": cen},
                        "drive_chain_id": None,
                        "health": HealthState.UNKNOWN.value,
                        "reason": {
                            "zh": "部件模板：暂无遥测信号",
                            "en": "Component template: no telemetry yet",
                        },
                        "lifecycle_id": None,
                        "lifecycles": [],
                        "maintenance": [],
                        "signals": [],
                        "trend": [],
                    }
                )
        machines.append(
            {
                "machine_id": machine_id,
                "name": {"zh": zh, "en": en},
                "scenario_id": sid,
                "scenario_title": meta["title"],
                "snapshot_at": snapshot_iso,
                "components": components,
            }
        )
    return {"is_simulated": True, "health_basis": HEALTH_BASIS.model_dump(), "machines": machines}


def write_fleet(data_dir: Path) -> Path:
    path = data_dir / "fixtures" / "demo_fleet.json"
    path.write_bytes((json.dumps(build_fleet(data_dir), indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    return path
