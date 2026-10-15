"""D-042: the online pipeline turns mapped source data into features, steadily across runs and steps."""

from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.main  # noqa: F401  (registers tables)
from app.core.db import Base
from app.datasource.query_service.sources import DataSourceRegistry
from app.decision.pipeline import run_machine
from app.equipment.lifecycle import EquipmentStore
from app.equipment.schemas import ComponentInstance, Machine
from app.monitoring.features.store import FeatureStore
from app.signals.registry import SignalConfigStore
from app.signals.schemas import DeviceConfigChange
from app.simulation.demo_pipeline import (
    DEMO_FLEET,
    SETUP,
    SOURCE_ID,
    add_demo_source,
    demo_machines,
)
from app.simulation.golden import DATA_DIR


def setup(tmp_path, name):
    (m,) = demo_machines(DATA_DIR, [r for r in DEMO_FLEET if r[1] == "S04"])
    sources = DataSourceRegistry()
    add_demo_source(sources, [m])
    engine = create_engine(f"sqlite:///{tmp_path}/{name}.db")
    Base.metadata.create_all(engine)
    s = Session(engine)
    eq = EquipmentStore(s)
    eq.put_machine(Machine(machine_id=m.machine_id, name=m.name, line="SIM", is_simulated=True), SETUP)
    for c in m.topology["components"]:
        comp = ComponentInstance(**{k: v for k, v in c.items() if k in ComponentInstance.model_fields})
        eq.put_component(comp, SETUP)
        eq.install(comp.component_id, m.t0, SETUP, "SIMULATED")
    SignalConfigStore(s).replace_device(
        SOURCE_ID,
        m.topology["mappings"][0]["device_id"],
        DeviceConfigChange(
            comment="test", signals=[x for _, x in m.items], mappings=[mp for mp, _ in m.items]
        ),
        SETUP,
    )
    s.commit()
    return s, sources, m


def windows(s, m):
    fs = FeatureStore(s)
    return sorted(
        (c.component_id, v.window.start)
        for c in EquipmentStore(s).components(m.machine_id)
        for v in fs.vectors(c.component_id)
    )


def test_pending_until_the_catalog_period_has_data(tmp_path):
    s, sources, m = setup(tmp_path, "a")
    assert run_machine(s, sources, m.machine_id, until=m.t0 + timedelta(days=1)).catalog == "pending"
    assert windows(s, m) == []


def test_provisional_start_learns_the_catalog_from_the_data_there_is(tmp_path):
    s, sources, m = setup(tmp_path, "p")
    day3 = m.t0 + timedelta(days=3)
    wait = run_machine(s, sources, m.machine_id, until=day3)
    assert wait.catalog == "pending" and wait.ready_at == m.t0 + timedelta(days=4) and not wait.provisional
    short = run_machine(s, sources, m.machine_id, until=m.t0 + timedelta(hours=12), provisional=True)
    assert short.catalog == "pending"  # less than a day of data is not enough even provisionally
    r = run_machine(s, sources, m.machine_id, until=day3, provisional=True, max_steps=40)
    assert r.catalog == "ready" and r.provisional and r.windows_added > 0
    assert windows(s, m)  # a young component can now be checked and validated


def test_steps_and_repeated_runs_give_the_same_windows(tmp_path):
    a, sources, m = setup(tmp_path, "a")
    b, _, _ = setup(tmp_path, "b")
    mid = m.t0 + timedelta(days=12)
    run_machine(a, sources, m.machine_id, until=mid, max_steps=400)
    first = windows(a, m)
    r = run_machine(a, sources, m.machine_id, until=m.end, max_steps=400)
    again = run_machine(a, sources, m.machine_id, until=m.end, max_steps=400)
    run_machine(b, sources, m.machine_id, until=m.end, step_hours=24 * 60, max_steps=400)
    assert first and r.catalog == "ready" and r.windows_added > 0
    assert again.windows_added == 0  # nothing new: nothing changes
    assert windows(a, m) == windows(b, m)
    assert len(windows(a, m)) > len(first)


def test_without_a_verified_reference_components_are_listed(tmp_path):
    s, sources, m = setup(tmp_path, "a")
    r = run_machine(s, sources, m.machine_id, until=m.end, max_steps=400)
    assert r.no_reference and r.is_simulated
