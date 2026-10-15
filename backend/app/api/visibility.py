"""What the current run mode lets a screen list (D-053).

Simulation mode shows only simulated machines and sources, production mode only real ones. A machine is
simulated when it is flagged so or all its mapped signals come from simulated sources; a machine with
nothing mapped yet belongs to both modes, so a machine just created can still be configured. This is
applied where lists are built; looking something up by id is not hidden.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.runmode import RunMode, get_mode
from app.datasource.query_service.sources import DataSourceRegistry
from app.datasource.schemas import DataSourceConfig, DataSourceKind
from app.decision.schemas import FleetOverview
from app.equipment.lifecycle import EquipmentStore
from app.equipment.plant import PlantMachine, PlantProcess, PlantTree, PlantWorkshop
from app.equipment.schemas import Machine
from app.signals.registry import SignalConfigStore
from app.signals.schemas import SignalConfigState


def source_in_mode(config: DataSourceConfig, mode: RunMode) -> bool:
    simulated = config.kind == DataSourceKind.SIMULATED
    return simulated if mode == RunMode.SIMULATION else not simulated


class Visibility:
    def __init__(self, session: Session, sources: DataSourceRegistry, mode: RunMode):
        self.session, self.sources, self.mode = session, sources, mode
        self._kind = {c.data_source_id: c.kind for c in sources.configs()}
        self._by_component: dict[str, set[str]] | None = None

    def source_ok(self, data_source_id: str) -> bool:
        kind = self._kind.get(data_source_id)
        if kind is None:
            return self.mode == RunMode.PRODUCTION  # a source that is not loaded cannot be a simulated one
        return (kind == DataSourceKind.SIMULATED) == (self.mode == RunMode.SIMULATION)

    def _bound(self) -> dict[str, set[str]]:
        if self._by_component is None:
            self._by_component = {}
            for m in SignalConfigStore(self.session).current().content.mappings:
                if m.component_id:
                    self._by_component.setdefault(m.component_id, set()).add(m.data_source_id)
        return self._by_component

    def machine_ok(self, machine_id: str, flagged_simulated: bool, component_ids: list[str]) -> bool:
        sources = {s for c in component_ids for s in self._bound().get(c, set())}
        if flagged_simulated or (
            sources and all(self._kind.get(s) == DataSourceKind.SIMULATED for s in sources)
        ):
            return self.mode == RunMode.SIMULATION
        if sources:
            return self.mode == RunMode.PRODUCTION
        return True  # nothing mapped yet: belongs to both

    def machines(self) -> list[Machine]:
        store = EquipmentStore(self.session)
        comps: dict[str, list[str]] = {}
        for c in store.components():
            comps.setdefault(c.machine_id, []).append(c.component_id)
        return [
            m
            for m in store.machines()
            if self.machine_ok(m.machine_id, m.is_simulated, comps.get(m.machine_id, []))
        ]

    def machine_ids(self) -> set[str]:
        return {m.machine_id for m in self.machines()}

    def fleet(self, fleet: FleetOverview) -> FleetOverview:
        keep = self.machine_ids()
        return fleet.model_copy(update={"machines": [m for m in fleet.machines if m.machine_id in keep]})

    def plant(self, tree: PlantTree) -> PlantTree:
        keep = self.machine_ids()

        def mach(ms: list[PlantMachine]) -> list[PlantMachine]:
            return [m for m in ms if m.machine_id in keep]

        workshops = []
        for w in tree.workshops:
            procs = []
            for p in w.processes:
                kept = mach(p.machines)
                if kept or not p.machines:  # an emptied-by-mode node is hidden; a node never used stays
                    procs.append(PlantProcess(node_id=p.node_id, name=p.name, sort=p.sort, machines=kept))
            if procs or not w.processes:
                workshops.append(PlantWorkshop(node_id=w.node_id, name=w.name, sort=w.sort, processes=procs))
        return PlantTree(workshops=workshops, unplaced=mach(tree.unplaced))

    def signal_config(self, state: SignalConfigState) -> SignalConfigState:
        c = state.content
        hidden = {m.signal_id for m in c.mappings if not self.source_ok(m.data_source_id)}
        if not hidden:
            return state
        content = c.model_copy(
            update={
                "signals": [s for s in c.signals if s.signal_id not in hidden],
                "mappings": [m for m in c.mappings if m.signal_id not in hidden],
                "groups": [g for g in c.groups if not hidden & set(g.signal_ids)],
                "visualizations": [v for v in c.visualizations if not hidden & set(v.signal_ids)],
            }
        )
        return state.model_copy(update={"content": content})


def _sources(request: Request) -> DataSourceRegistry:
    return request.app.state.sources


def visibility(request: Request, db: Annotated[Session, Depends(get_session)]) -> Visibility:
    return Visibility(db, _sources(request), get_mode(db))


Visible = Annotated[Visibility, Depends(visibility)]
