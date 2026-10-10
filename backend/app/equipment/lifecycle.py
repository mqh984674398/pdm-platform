"""Topology and component lifecycles (L3-01, L3-06), persisted with an audit trail (SEC-02).

A lifecycle is one physical installation of a component. Lifecycles are never edited away: a
replacement retires the current one and starts its successor (see ``maintenance.py``), so the history
of every installation stays readable. Lubrication and other non-replacing maintenance leave the
lifecycle and its accumulated operation untouched, so aging is never reset by them (L3-08).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.audit import record as audit
from app.core.db import Base
from app.core.schemas import LocalizedText
from app.core.security import Principal
from app.equipment.schemas import (
    ComponentAging,
    ComponentInstance,
    ComponentLifecycle,
    ComponentType,
    LifecycleStatus,
    Machine,
    OperatingState,
    StateSegment,
    UsageRecord,
)


class EquipmentNotFoundError(LookupError):
    pass


class EquipmentConflictError(ValueError):
    """The change contradicts the recorded topology, lifecycle history, or maintenance history."""


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


class MachineRecord(Base):
    __tablename__ = "machines"

    machine_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    line: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_simulated: Mapped[bool] = mapped_column(nullable=False)

    def to_model(self) -> Machine:
        return Machine(
            machine_id=self.machine_id,
            name=LocalizedText.model_validate(self.name),
            line=self.line,
            is_simulated=self.is_simulated,
        )


class ComponentRecord(Base):
    __tablename__ = "components"

    component_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.machine_id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    drive_chain_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signal_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    def to_model(self) -> ComponentInstance:
        return ComponentInstance(
            component_id=self.component_id,
            machine_id=self.machine_id,
            type=ComponentType(self.type),
            name=LocalizedText.model_validate(self.name),
            drive_chain_id=self.drive_chain_id,
            signal_ids=list(self.signal_ids),
        )


class LifecycleRecord(Base):
    __tablename__ = "component_lifecycles"
    __table_args__ = (UniqueConstraint("component_id", "seq", name="uq_component_lifecycles_component_seq"),)

    lifecycle_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    component_id: Mapped[str] = mapped_column(
        ForeignKey("components.component_id"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    predecessor_lifecycle_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    accumulated_operating_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    accumulated_cycles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usage_counted_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def to_model(self) -> ComponentLifecycle:
        return ComponentLifecycle(
            lifecycle_id=self.lifecycle_id,
            component_id=self.component_id,
            installed_at=_aware(self.installed_at),
            retired_at=_aware(self.retired_at),
            predecessor_lifecycle_id=self.predecessor_lifecycle_id,
            status=LifecycleStatus(self.status),
            accumulated_operating_hours=self.accumulated_operating_hours,
            accumulated_cycles=self.accumulated_cycles,
            usage_counted_until=_aware(self.usage_counted_until),
        )


def lifecycle_id(component_id: str, seq: int) -> str:
    return f"{component_id}-LC{seq}"


class EquipmentStore:
    def __init__(self, session: Session):
        self.session = session

    # --- topology (L3-01) ----------------------------------------------------------------------

    def machines(self) -> list[Machine]:
        return [
            r.to_model()
            for r in self.session.scalars(select(MachineRecord).order_by(MachineRecord.machine_id))
        ]

    def machine(self, machine_id: str) -> Machine:
        rec = self.session.get(MachineRecord, machine_id)
        if rec is None:
            raise EquipmentNotFoundError(f"machine '{machine_id}' does not exist")
        return rec.to_model()

    def put_machine(self, m: Machine, who: Principal) -> Machine:
        rec = self.session.get(MachineRecord, m.machine_id)
        action = "update" if rec else "create"
        if rec is None:
            rec = MachineRecord(machine_id=m.machine_id)
            self.session.add(rec)
        elif rec.is_simulated != m.is_simulated:
            raise EquipmentConflictError("a machine cannot switch between simulated and real")
        rec.name, rec.line, rec.is_simulated = m.name.model_dump(), m.line, m.is_simulated
        audit(self.session, who, f"topology.machine_{action}", "machine", m.machine_id)
        return rec.to_model()

    def components(self, machine_id: str | None = None) -> list[ComponentInstance]:
        stmt = select(ComponentRecord).order_by(ComponentRecord.component_id)
        if machine_id:
            stmt = stmt.where(ComponentRecord.machine_id == machine_id)
        return [r.to_model() for r in self.session.scalars(stmt)]

    def component(self, component_id: str) -> ComponentInstance:
        return self._component(component_id).to_model()

    def _component(self, component_id: str) -> ComponentRecord:
        rec = self.session.get(ComponentRecord, component_id)
        if rec is None:
            raise EquipmentNotFoundError(f"component '{component_id}' does not exist")
        return rec

    def put_component(self, c: ComponentInstance, who: Principal) -> ComponentInstance:
        self.machine(c.machine_id)
        rec = self.session.get(ComponentRecord, c.component_id)
        action = "update" if rec else "create"
        if rec is None:
            rec = ComponentRecord(component_id=c.component_id)
            self.session.add(rec)
        else:
            if rec.machine_id != c.machine_id:
                raise EquipmentConflictError("a component cannot move to another machine; create a new one")
            if rec.type != c.type.value:
                raise EquipmentConflictError("a component's type cannot change; create a new one")
        rec.machine_id, rec.type, rec.name = c.machine_id, c.type.value, c.name.model_dump()
        rec.drive_chain_id, rec.signal_ids = c.drive_chain_id, list(c.signal_ids)
        audit(self.session, who, f"topology.component_{action}", "component", c.component_id)
        return rec.to_model()

    def is_simulated(self, component_id: str) -> bool:
        comp = self._component(component_id)
        return self.session.get(MachineRecord, comp.machine_id).is_simulated  # type: ignore[union-attr]

    # --- lifecycles (L3-06) --------------------------------------------------------------------

    def _lifecycles(self, component_id: str) -> list[LifecycleRecord]:
        stmt = select(LifecycleRecord).where(LifecycleRecord.component_id == component_id)
        return list(self.session.scalars(stmt.order_by(LifecycleRecord.seq)))

    def lifecycles(self, component_id: str) -> list[ComponentLifecycle]:
        self._component(component_id)
        return [r.to_model() for r in self._lifecycles(component_id)]

    def lifecycle(self, lifecycle_id: str) -> ComponentLifecycle:
        return self._lifecycle(lifecycle_id).to_model()

    def _lifecycle(self, lid: str) -> LifecycleRecord:
        rec = self.session.get(LifecycleRecord, lid)
        if rec is None:
            raise EquipmentNotFoundError(f"lifecycle '{lid}' does not exist")
        return rec

    def active_record(self, component_id: str) -> LifecycleRecord:
        active = [r for r in self._lifecycles(component_id) if r.status == LifecycleStatus.ACTIVE.value]
        if not active:
            raise EquipmentConflictError(f"component '{component_id}' has no installed lifecycle")
        return active[-1]

    def lifecycle_at(self, component_id: str, at: datetime) -> ComponentLifecycle:
        for r in self._lifecycles(component_id):
            lc = r.to_model()
            if lc.installed_at <= at and (lc.retired_at is None or at < lc.retired_at):
                return lc
        raise EquipmentNotFoundError(f"component '{component_id}' was not installed at {at.isoformat()}")

    def install(
        self, component_id: str, installed_at: datetime, who: Principal, comment: str = ""
    ) -> ComponentLifecycle:
        self._component(component_id)
        if self._lifecycles(component_id):
            raise EquipmentConflictError(
                "the component already has lifecycles; a new installation is recorded as a REPLACEMENT event"
            )
        rec = self._new_lifecycle(component_id, 1, installed_at, None)
        audit(
            self.session,
            who,
            "lifecycle.install",
            "component_lifecycle",
            rec.lifecycle_id,
            component_id=component_id,
            installed_at=installed_at.isoformat(),
            comment=comment,
        )
        return rec.to_model()

    def _new_lifecycle(
        self, component_id: str, seq: int, at: datetime, predecessor: str | None
    ) -> LifecycleRecord:
        rec = LifecycleRecord(
            lifecycle_id=lifecycle_id(component_id, seq),
            component_id=component_id,
            seq=seq,
            installed_at=at,
            predecessor_lifecycle_id=predecessor,
            status=LifecycleStatus.ACTIVE.value,
            accumulated_operating_hours=0.0,
            accumulated_cycles=0,
            usage_counted_until=at,
        )
        self.session.add(rec)
        self.session.flush()
        return rec

    def replace(self, component_id: str, at: datetime) -> tuple[LifecycleRecord, LifecycleRecord]:
        """Retire the active lifecycle at ``at`` and start its successor. The caller audits."""
        old = self.active_record(component_id)
        if at <= _aware(old.installed_at):
            raise EquipmentConflictError("a replacement must come after the current installation")
        if old.usage_counted_until and at < _aware(old.usage_counted_until):
            raise EquipmentConflictError(
                "operation after this time is already counted for the current lifecycle"
            )
        old.status, old.retired_at = LifecycleStatus.RETIRED.value, at
        new = self._new_lifecycle(component_id, old.seq + 1, at, old.lifecycle_id)
        return old, new

    def record_usage(self, lid: str, usage: UsageRecord, who: Principal) -> ComponentLifecycle:
        """Add operation for (usage_counted_until, until]; each period is counted once."""
        rec = self._lifecycle(lid)
        start = _aware(rec.usage_counted_until) or _aware(rec.installed_at)
        end_limit = _aware(rec.retired_at)
        if usage.until <= start:  # type: ignore[operator]
            raise EquipmentConflictError(f"operation up to {start.isoformat()} is already counted")  # type: ignore[union-attr]
        if end_limit is not None and usage.until > end_limit:
            raise EquipmentConflictError("usage extends past the lifecycle's retirement")
        hours = (usage.until - start).total_seconds() / 3600  # type: ignore[operator]
        if usage.operating_hours > hours + 1e-9:
            raise EquipmentConflictError("more operating hours than the period has")
        rec.accumulated_operating_hours += usage.operating_hours
        rec.accumulated_cycles += usage.cycles
        rec.usage_counted_until = usage.until
        audit(
            self.session,
            who,
            "lifecycle.usage",
            "component_lifecycle",
            lid,
            since=start.isoformat(),  # type: ignore[union-attr]
            until=usage.until.isoformat(),
            operating_hours=usage.operating_hours,
            cycles=usage.cycles,
            source=usage.source,
        )
        return rec.to_model()

    def aging(
        self, component_id: str, at: datetime, maintenance_times: Sequence[datetime] = ()
    ) -> ComponentAging:
        """Age of the lifecycle installed at ``at``. ``maintenance_times``: events on that lifecycle."""
        lc = self.lifecycle_at(component_id, at)
        done = sorted(t for t in maintenance_times if lc.installed_at <= t <= at)
        return ComponentAging(
            component_id=component_id,
            lifecycle_id=lc.lifecycle_id,
            installed_at=lc.installed_at,
            at=at,
            calendar_hours=(at - lc.installed_at).total_seconds() / 3600,
            operating_hours=lc.accumulated_operating_hours,
            cycles=lc.accumulated_cycles,
            maintenance_since_install=len(done),
            last_maintenance_at=done[-1] if done else None,
        )


def running_hours(segments: Sequence[StateSegment], start: datetime, end: datetime) -> float:
    """Derived RUNNING time inside [start, end) (T013 states), in hours."""
    total = 0.0
    for s in segments:
        if s.state == OperatingState.RUNNING:
            a, b = max(s.start, start), min(s.end, end)
            total += max((b - a).total_seconds(), 0.0)
    return total / 3600
