"""SIMULATED end-to-end demo pipeline (T020): simulated adapter -> features -> rules -> alarms -> UI.

Each demo machine replays one simulated scenario through the same services the API uses, in time
order, and stores every result in the application database:

1. topology, first installation and the scenario's maintenance events (replacements start lifecycles);
2. the signal configuration for the machine's simulated device;
3. a regime catalog learned from the first 96 h, then feature vectors for the rest of the scenario;
4. a verified healthy reference per lifecycle, created through the audited verification by the
   labeled ``demo-engineer (SIMULATED)`` account. This stands in for an engineer's judgment so the
   demo can run; it is not a real verification and is marked as such in its comment;
5. rule evaluation and alarm synchronization (no notifications);
6. maintenance workflows advanced by the impact analysis at the times the workflow would be checked.

Everything is simulated data. Nothing here connects to a production source.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.schemas import LocalizedText, TimeWindow
from app.core.security import Principal, Role
from app.datasource.query_service.sources import DataSourceRegistry
from app.datasource.schemas import DataSourceConfig, DataSourceKind
from app.datasource.simulated import SimulatedAdapter
from app.equipment.lifecycle import EquipmentStore
from app.equipment.maintenance import MaintenanceService
from app.equipment.maintenance_impact.service import ImpactService
from app.equipment.regimes import learn_catalog
from app.equipment.schemas import (
    ComponentInstance,
    ComponentType,
    ImpactConfig,
    Machine,
    MaintenanceEventCreate,
    MaintenanceEventType,
)
from app.equipment.state import load_series
from app.monitoring.alarms.service import AlarmService
from app.monitoring.baselines.verified import BaselineError, BaselineService
from app.monitoring.features.extract import extract_features
from app.monitoring.features.store import FeatureStore
from app.monitoring.rules.definitions import DEFAULT_RULES
from app.monitoring.rules.engine import evaluate
from app.monitoring.rules.settings import RuleSettings
from app.monitoring.schemas import BaselineVerification
from app.signals.registry import SignalConfigStore
from app.signals.schemas import DeviceConfigChange, SignalDefinition, SignalMapping
from app.simulation.demo_fleet import FLEET

SOURCE_ID = "sim-fleet"
# machine id, scenario id, name zh, en. A01-A08 as in the T007 fixture; A09-A11 add the maintenance
# outcomes reviewed at G3 (lubrication improvement and deterioration, partial repair).
DEMO_FLEET = [(m, s, zh, en) for m, s, _, zh, en in FLEET] + [
    ("A09", "S09", "9号装配机", "Assembly machine 9"),
    ("A10", "S10", "10号装配机", "Assembly machine 10"),
    ("A11", "S11", "11号压装机", "Press-fit machine 11"),
]
# Periods for scenarios observed 4 windows a day; scaled so sparser scenarios get as many windows.
CATALOG_H = 96.0  # regime catalog learned from the first four days
REFERENCE_H = (96.0, 168.0)  # first lifecycle: the three days after the regime reference
NEW_LIFECYCLE_REFERENCE_H = (24.0, 96.0)  # later lifecycles: after installation and run-in
BASE_WINDOWS_PER_DAY = 4
SETUP = Principal(user_id="demo-pipeline (SIMULATED)", role=Role.ADMIN)
DEMO_ENGINEER = Principal(user_id="demo-engineer (SIMULATED)", role=Role.ENGINEER)
TECHNICIAN = Principal(user_id="sim-technician (SIMULATED)", role=Role.MAINTENANCE)
MONITOR = Principal(user_id="system:monitoring", role=Role.ENGINEER)
VERIFY_COMMENT = (
    "SIMULATED demo: verified by the demo pipeline on behalf of an engineer, using the scenario's "
    "known-healthy period. Not a real engineering verification."
)


def _ts(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


@dataclass
class DemoMachine:
    machine_id: str
    scenario_id: str
    name: LocalizedText
    dir: Path
    topology: dict
    events: list[dict]
    maintenance_hours: dict[str, float]
    t0: datetime
    hours: float
    scale: float = 1.0  # BASE_WINDOWS_PER_DAY / the scenario's windows per day

    def window(self, a: float, b: float) -> TimeWindow:
        return TimeWindow(start=self.t0 + timedelta(hours=a), end=self.t0 + timedelta(hours=b))

    @property
    def end(self) -> datetime:
        return self.t0 + timedelta(hours=self.hours)

    @property
    def items(self) -> list[tuple[SignalMapping, SignalDefinition]]:
        signals = {s["signal_id"]: SignalDefinition(**s) for s in self.topology["signals"]}
        return [(SignalMapping(**m), signals[m["signal_id"]]) for m in self.topology["mappings"]]


def _rename(text: str, machine_id: str) -> str:
    """Scenario ids (M01, M01-BS1, ...) to the demo machine's ids; device and key names stay."""
    return text.replace('"M01"', f'"{machine_id}"').replace("M01-", f"{machine_id}-")


def load_machine(data_dir: Path, machine_id: str, scenario_id: str, zh: str, en: str) -> DemoMachine:
    d = next((data_dir / "scenarios").glob(f"{scenario_id}_*"))
    topo = json.loads(_rename((d / "topology.json").read_text(encoding="utf-8"), machine_id))
    for m in topo["mappings"]:
        m["data_source_id"] = SOURCE_ID
    events = json.loads(_rename((d / "maintenance_events.json").read_text(encoding="utf-8"), machine_id))
    cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
    durations = {
        f"{machine_id}-{m['component_id'].split('-', 1)[1]}@{m['at_h']}": m["duration_h"]
        for m in cfg.get("maintenance", [])
    }
    t0 = _ts(cfg["start"])
    hours = {
        e["event_id"]: durations.get(
            f"{e['component_id']}@{(_ts(e['performed_at']) - t0).total_seconds() / 3600}", 0.5
        )
        for e in events
    }
    return DemoMachine(
        machine_id=machine_id,
        scenario_id=scenario_id,
        name=LocalizedText(zh=zh, en=en),
        dir=d,
        topology=topo,
        events=events,
        maintenance_hours=hours,
        t0=t0,
        hours=float(cfg["duration_hours"]),
        scale=BASE_WINDOWS_PER_DAY / float(cfg["observation"]["windows_per_day"]),
    )


def demo_machines(
    data_dir: Path, fleet: Sequence[tuple[str, str, str, str]] = DEMO_FLEET
) -> list[DemoMachine]:
    return [load_machine(data_dir, *row) for row in fleet]


def add_demo_source(sources: DataSourceRegistry, machines: Sequence[DemoMachine]) -> None:
    config = DataSourceConfig(
        data_source_id=SOURCE_ID,
        name="SIM demo fleet",
        kind=DataSourceKind.SIMULATED,
        read_only=True,
        is_simulated=True,
        max_rows=2_000_000,
    )
    sources.add(config, SimulatedAdapter([m.dir for m in machines], SOURCE_ID))


@dataclass
class MachineResult:
    machine_id: str
    vectors: int
    references: list[str]
    alarms_raised: int
    workflows: dict[str, str]


def _reference_window(m: DemoMachine, installed_at: datetime, seq: int) -> TimeWindow:
    if seq == 1:
        return m.window(REFERENCE_H[0] * m.scale, REFERENCE_H[1] * m.scale)
    a, b = (h * m.scale for h in NEW_LIFECYCLE_REFERENCE_H)
    return TimeWindow(start=installed_at + timedelta(hours=a), end=installed_at + timedelta(hours=b))


def run_machine(session: Session, sources: DataSourceRegistry, m: DemoMachine) -> MachineResult:
    equipment = EquipmentStore(session)
    topo = m.topology
    equipment.put_machine(Machine(machine_id=m.machine_id, name=m.name, line=f"SIM-{m.scenario_id}",
                                  is_simulated=True), SETUP)  # fmt: skip
    types: dict[str, ComponentType] = {}
    for c in topo["components"]:
        comp = ComponentInstance(**{k: v for k, v in c.items() if k in ComponentInstance.model_fields})
        equipment.put_component(comp, SETUP)
        equipment.install(comp.component_id, m.t0, SETUP, "SIMULATED demo installation")
        types[comp.component_id] = comp.type

    device = topo["mappings"][0]["device_id"]
    items = m.items
    SignalConfigStore(session).replace_device(
        SOURCE_ID,
        device,
        DeviceConfigChange(
            comment=f"SIMULATED demo machine {m.machine_id} ({m.scenario_id})",
            signals=[s for _, s in items],
            mappings=[mp for mp, _ in items],
        ),
        SETUP,
    )

    maintenance = MaintenanceService(session)
    windows = []
    for e in sorted(m.events, key=lambda e: e["performed_at"]):
        at = _ts(e["performed_at"])
        res = maintenance.record_event(
            MaintenanceEventCreate(component_id=e["component_id"], type=MaintenanceEventType(e["type"]),
                                   performed_at=at, notes="SIMULATED maintenance event"),
            TECHNICIAN, event_id=f"{m.machine_id}-{e['event_id']}", now=at,
        )  # fmt: skip
        windows.append((at, at + timedelta(hours=m.maintenance_hours[e["event_id"]]), res.event.event_id))

    series = load_series(sources, items, m.window(0, m.hours))
    catalog_h = CATALOG_H * m.scale
    catalog = learn_catalog(series, m.machine_id, m.window(0, catalog_h), f"{m.machine_id}-ref")
    lifecycles = {
        cid: [(lc.lifecycle_id, lc.installed_at, lc.retired_at) for lc in equipment.lifecycles(cid)]
        for cid in types
    }
    extraction = extract_features(series, m.window(catalog_h, m.hours), types, lifecycles, catalog, windows)
    store = FeatureStore(session)
    store.register_all()
    store.save(extraction.vectors, now=m.end)

    baselines, refs = BaselineService(session), []
    settings = RuleSettings(session)
    evaluations = []
    for cid in types:
        vectors = [v for v in extraction.vectors if v.component_id == cid]
        if not vectors:
            continue
        ref_by_lc = {}
        for lc in equipment.lifecycles(cid):
            window = _reference_window(m, lc.installed_at, int(lc.lifecycle_id.rsplit("LC", 1)[1]))
            if window.end > m.end:
                continue
            req = BaselineVerification(component_id=cid, lifecycle_id=lc.lifecycle_id,
                                       feature_ref=vectors[0].feature_ref, window=window,
                                       comment=VERIFY_COMMENT)  # fmt: skip
            try:
                ref = baselines.verify(req, DEMO_ENGINEER, now=window.end)
            except BaselineError:
                continue  # too few healthy windows: the lifecycle stays without a reference (UNKNOWN)
            ref_by_lc[lc.lifecycle_id] = ref
            refs.append(ref.baseline_id)
        evaluations += evaluate(vectors, ref_by_lc, DEFAULT_RULES, settings.disabled(),
                                rules_version=settings.config_version())  # fmt: skip
    raised, _ = AlarmService(session).sync(evaluations, MONITOR)

    impact, cfg = ImpactService(session), ImpactConfig()
    outcomes = {}
    for cid in types:
        for wf in maintenance.workflows(cid):
            event_at = next(w[0] for w in windows if f"WF-{w[2]}" == wf.workflow_id)
            checks = [0.0, cfg.stabilization_hours, cfg.stabilization_hours + cfg.validation_hours]
            checks += [cfg.stabilization_hours + cfg.max_validation_hours]
            state = wf
            for h in checks:
                at = min(event_at + timedelta(hours=h), m.end)
                state = impact.advance(wf.workflow_id, series, catalog, now=at, config=cfg)
            outcomes[wf.workflow_id] = state.state.value
    session.flush()
    return MachineResult(m.machine_id, len(extraction.vectors), refs, len(raised), outcomes)


def run_pipeline(
    session: Session, sources: DataSourceRegistry, machines: Sequence[DemoMachine]
) -> list[MachineResult]:
    out = []
    for m in machines:
        out.append(run_machine(session, sources, m))
        session.commit()
    return out
