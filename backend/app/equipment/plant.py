"""Plant structure: workshop (车间) → process (工序) → machine (机台), configured by administrators (D-037).

The tree places machines for people: the Studio offers it as a way to pick a device, and the fleet,
machine map and component history show a machine's workshop / process path. Each machine can carry
the device id it has in the data source (for example a TDengine tag value), so a device picked from
the database and a machine picked from the tree resolve to the same thing.

Administrators also maintain each machine's components here, including which components share a
drive chain; that is what the machine map draws and what the common-cause check reads (D-038).
Every change is audited.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import Field
from sqlalchemy import JSON, ForeignKey, Integer, String, delete, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.audit import record as audit
from app.core.db import Base
from app.core.schemas import ContractModel, LocalizedText
from app.core.security import Principal, Role
from app.equipment.lifecycle import (
    ComponentRecord,
    EquipmentConflictError,
    EquipmentNotFoundError,
    MachineRecord,
)
from app.equipment.schemas import ComponentInstance, ComponentType, Machine

ID = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"
ID_RE = re.compile(ID)


class PlantPermissionError(PermissionError):
    pass


class PlantLevel(StrEnum):
    WORKSHOP = "WORKSHOP"
    PROCESS = "PROCESS"


class PlantNodeRecord(Base):
    __tablename__ = "plant_nodes"

    node_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("plant_nodes.node_id"), nullable=True, index=True
    )
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PlantNodeChange(ContractModel):
    node_id: str = Field(pattern=ID)
    parent_id: str | None = Field(default=None, description="Workshop of a process; None for a workshop")
    level: PlantLevel
    name: LocalizedText
    sort: int = 0


class PlantMachine(ContractModel):
    machine_id: str
    name: LocalizedText
    device_id: str | None
    is_simulated: bool
    components: list[ComponentInstance]


class PlantProcess(ContractModel):
    node_id: str
    name: LocalizedText
    sort: int
    machines: list[PlantMachine]


class PlantWorkshop(ContractModel):
    node_id: str
    name: LocalizedText
    sort: int
    processes: list[PlantProcess]


class PlantTree(ContractModel):
    workshops: list[PlantWorkshop]
    unplaced: list[PlantMachine] = Field(description="Machines not yet assigned to a process")


class MachineCreate(ContractModel):
    machine_id: str = Field(pattern=ID)
    name: LocalizedText
    process_id: str
    device_id: str | None = Field(default=None, max_length=128)


class MachinePlacement(ContractModel):
    process_id: str | None
    device_id: str | None = Field(default=None, max_length=128)
    name: LocalizedText | None = None


PROTECTED_TABLES = frozenset({"maintenance_events", "maintenance_workflows"})  # real history: never cascaded


class UsageRow(ContractModel):
    kind: str  # table name, e.g. component_lifecycles, feature_vectors, alarms
    count: int
    blocks: bool = False  # true: deleting the component is refused while these exist


class ComponentUsage(ContractModel):
    component_id: str
    rows: list[UsageRow]
    deletable: bool


class ComponentChange(ContractModel):
    """What an administrator sets for a component; lifecycles and signals are kept."""

    component_id: str = Field(pattern=ID)
    type: ComponentType
    name: LocalizedText
    drive_chain_id: str | None = Field(default=None, pattern=ID)
    torque_limit: float | None = Field(
        default=None, gt=0, description="Allowed torque in the unit of the torque signal (SF-TORQUE-LIMIT)"
    )


def process_paths(session: Session) -> dict[str, LocalizedText]:
    """process node id → "workshop / process" in both languages."""
    nodes = {n.node_id: n for n in session.scalars(select(PlantNodeRecord))}
    out: dict[str, LocalizedText] = {}
    for n in nodes.values():
        if n.level != PlantLevel.PROCESS:
            continue
        ws = nodes.get(n.parent_id or "")
        p = LocalizedText.model_validate(n.name)
        if ws is None:
            out[n.node_id] = p
            continue
        w = LocalizedText.model_validate(ws.name)
        out[n.node_id] = LocalizedText(zh=f"{w.zh} / {p.zh}", en=f"{w.en} / {p.en}")
    return out


class PlantStore:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _admin(who: Principal) -> None:
        if not who.at_least(Role.ADMIN):
            raise PlantPermissionError("changing the plant structure requires an administrator")

    # --- read ----------------------------------------------------------------------------------

    def tree(self) -> PlantTree:
        nodes = list(
            self.session.scalars(
                select(PlantNodeRecord).order_by(PlantNodeRecord.sort, PlantNodeRecord.node_id)
            )
        )
        comps: dict[str, list[ComponentInstance]] = {}
        for c in self.session.scalars(select(ComponentRecord).order_by(ComponentRecord.component_id)):
            comps.setdefault(c.machine_id, []).append(c.to_model())
        by_process: dict[str | None, list[PlantMachine]] = {}
        for m in self.session.scalars(select(MachineRecord).order_by(MachineRecord.machine_id)):
            by_process.setdefault(m.process_id, []).append(
                PlantMachine(
                    machine_id=m.machine_id,
                    name=LocalizedText.model_validate(m.name),
                    device_id=m.device_id,
                    is_simulated=m.is_simulated,
                    components=comps.get(m.machine_id, []),
                )
            )
        processes = [n for n in nodes if n.level == PlantLevel.PROCESS]
        workshops = [
            PlantWorkshop(
                node_id=w.node_id,
                name=LocalizedText.model_validate(w.name),
                sort=w.sort,
                processes=[
                    PlantProcess(
                        node_id=p.node_id,
                        name=LocalizedText.model_validate(p.name),
                        sort=p.sort,
                        machines=by_process.get(p.node_id, []),
                    )
                    for p in processes
                    if p.parent_id == w.node_id
                ],
            )
            for w in nodes
            if w.level == PlantLevel.WORKSHOP
        ]
        known = {p.node_id for p in processes}
        unplaced = [m for pid, ms in by_process.items() if pid not in known for m in ms]
        return PlantTree(workshops=workshops, unplaced=sorted(unplaced, key=lambda m: m.machine_id))

    def _node(self, node_id: str) -> PlantNodeRecord:
        rec = self.session.get(PlantNodeRecord, node_id)
        if rec is None:
            raise EquipmentNotFoundError(f"plant node '{node_id}' does not exist")
        return rec

    def _machine(self, machine_id: str) -> MachineRecord:
        rec = self.session.get(MachineRecord, machine_id)
        if rec is None:
            raise EquipmentNotFoundError(f"machine '{machine_id}' does not exist")
        return rec

    # --- workshops and processes ---------------------------------------------------------------

    def put_node(self, change: PlantNodeChange, who: Principal) -> None:
        self._admin(who)
        if change.level == PlantLevel.WORKSHOP and change.parent_id:
            raise EquipmentConflictError("a workshop has no parent")
        if change.level == PlantLevel.PROCESS:
            if not change.parent_id or self._node(change.parent_id).level != PlantLevel.WORKSHOP:
                raise EquipmentConflictError("a process belongs to a workshop")
        rec = self.session.get(PlantNodeRecord, change.node_id)
        action = "update" if rec else "create"
        if rec is None:
            rec = PlantNodeRecord(node_id=change.node_id)
            self.session.add(rec)
        elif rec.level != change.level.value:
            raise EquipmentConflictError("a node cannot change between workshop and process")
        rec.parent_id, rec.level = change.parent_id, change.level.value
        rec.name, rec.sort = change.name.model_dump(), change.sort
        audit(
            self.session, who, f"plant.node_{action}", "plant_node", change.node_id, parent=change.parent_id
        )

    def delete_node(self, node_id: str, who: Principal) -> None:
        self._admin(who)
        rec = self._node(node_id)
        children = self.session.scalar(
            select(func.count()).select_from(PlantNodeRecord).where(PlantNodeRecord.parent_id == node_id)
        )
        machines = self.session.scalar(
            select(func.count()).select_from(MachineRecord).where(MachineRecord.process_id == node_id)
        )
        if children or machines:
            raise EquipmentConflictError("remove or move its processes and machines first")
        self.session.delete(rec)
        audit(self.session, who, "plant.node_delete", "plant_node", node_id)

    # --- machines ------------------------------------------------------------------------------

    def _check_process(self, process_id: str | None) -> None:
        if process_id is not None and self._node(process_id).level != PlantLevel.PROCESS:
            raise EquipmentConflictError("machines are placed under a process")

    def _check_device(self, device_id: str | None, machine_id: str) -> None:
        if not device_id:
            return
        other = self.session.scalars(
            select(MachineRecord).where(
                MachineRecord.device_id == device_id, MachineRecord.machine_id != machine_id
            )
        ).first()
        if other is not None:
            raise EquipmentConflictError(
                f"device '{device_id}' is already bound to machine '{other.machine_id}'"
            )

    def create_machine(self, body: MachineCreate, who: Principal) -> MachineRecord:
        self._admin(who)
        if self.session.get(MachineRecord, body.machine_id) is not None:
            raise EquipmentConflictError(f"machine '{body.machine_id}' already exists")
        self._check_process(body.process_id)
        self._check_device(body.device_id, body.machine_id)
        rec = MachineRecord(
            machine_id=body.machine_id,
            name=body.name.model_dump(),
            line=None,
            is_simulated=False,
            process_id=body.process_id,
            device_id=body.device_id or None,
        )
        self.session.add(rec)
        audit(self.session, who, "plant.machine_create", "machine", body.machine_id, process=body.process_id)
        return rec

    def place_machine(self, machine_id: str, body: MachinePlacement, who: Principal) -> MachineRecord:
        self._admin(who)
        rec = self._machine(machine_id)
        self._check_process(body.process_id)
        self._check_device(body.device_id, machine_id)
        rec.process_id, rec.device_id = body.process_id, body.device_id or None
        if body.name is not None:
            rec.name = body.name.model_dump()
        audit(
            self.session, who, "plant.machine_place", "machine", machine_id,
            process=body.process_id, device=body.device_id,
        )  # fmt: skip
        return rec

    def delete_machine(self, machine_id: str, who: Principal) -> None:
        self._admin(who)
        rec = self._machine(machine_id)
        if self.session.scalar(
            select(func.count()).select_from(ComponentRecord).where(ComponentRecord.machine_id == machine_id)
        ):
            raise EquipmentConflictError("delete the machine's components first")
        self.session.delete(rec)
        audit(self.session, who, "plant.machine_delete", "machine", machine_id)

    # --- components ----------------------------------------------------------------------------

    def put_component(self, machine_id: str, body: ComponentChange, who: Principal) -> ComponentInstance:
        self._admin(who)
        self._machine(machine_id)
        rec = self.session.get(ComponentRecord, body.component_id)
        action = "update" if rec else "create"
        if rec is None:
            rec = ComponentRecord(component_id=body.component_id, machine_id=machine_id, signal_ids=[])
            self.session.add(rec)
        elif rec.machine_id != machine_id:
            raise EquipmentConflictError("a component cannot move to another machine; create a new one")
        elif rec.type != body.type.value:
            raise EquipmentConflictError("a component's type cannot change; create a new one")
        rec.type, rec.name, rec.drive_chain_id = body.type.value, body.name.model_dump(), body.drive_chain_id
        rec.torque_limit = body.torque_limit
        audit(
            self.session, who, f"plant.component_{action}", "component", body.component_id,
            drive_chain=body.drive_chain_id, torque_limit=body.torque_limit,
        )  # fmt: skip
        return rec.to_model()

    def _component_tables(self) -> list[Any]:
        """Every table that carries a ``component_id`` (found from the metadata so new ones are covered)."""
        return [
            t
            for t in Base.metadata.sorted_tables
            if "component_id" in t.c and t.name != ComponentRecord.__tablename__
        ]

    def component_usage(self, component_id: str) -> ComponentUsage:
        if self.session.get(ComponentRecord, component_id) is None:
            raise EquipmentNotFoundError(f"component '{component_id}' does not exist")
        rows = []
        for t in self._component_tables():
            n = self.session.scalar(
                select(func.count()).select_from(t).where(t.c.component_id == component_id)
            )
            if n:
                rows.append(UsageRow(kind=t.name, count=int(n), blocks=t.name in PROTECTED_TABLES))
        return ComponentUsage(
            component_id=component_id,
            rows=rows,
            deletable=not any(r.blocks for r in rows),
        )

    def delete_component(self, component_id: str, who: Principal, *, cascade: bool = False) -> None:
        """Delete a component. Installation history, features, alarms, baselines and configuration versions
        go with it only when ``cascade`` is set; maintenance records are real history and always block."""
        self._admin(who)
        usage = self.component_usage(component_id)
        blocking = [r.kind for r in usage.rows if r.blocks]
        if blocking:
            raise EquipmentConflictError(
                f"component '{component_id}' has maintenance records ({', '.join(blocking)}); "
                "it cannot be deleted"
            )
        if usage.rows and not cascade:
            raise EquipmentConflictError(
                f"component '{component_id}' still has data ({', '.join(r.kind for r in usage.rows)}); "
                "confirm the cascading delete to remove it"
            )
        for t in self._component_tables():
            self.session.execute(delete(t).where(t.c.component_id == component_id))
        self.session.delete(self.session.get(ComponentRecord, component_id))
        audit(
            self.session, who, "plant.component_delete", "component", component_id,
            removed={r.kind: r.count for r in usage.rows},
        )  # fmt: skip


def machine_model(session: Session, rec: MachineRecord) -> Machine:
    return rec.to_model(process_paths(session).get(rec.process_id or ""))
