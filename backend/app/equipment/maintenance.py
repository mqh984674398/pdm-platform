"""Maintenance events and the post-maintenance workflow (L3-05, L3-07, L3-08), audited (SEC-02).

Events are append-only intervention records. Only REPLACEMENT changes the lifecycle: it retires the
installed lifecycle and starts a new one, keeping the old lifecycle, its events and its accumulated
operation as history. Lubrication, adjustment, partial repair and inspection keep the lifecycle and
never reset its aging.

Every event except INSPECTION starts a workflow in MAINTENANCE_EVENT. Transitions follow
``WORKFLOW_TRANSITIONS`` exactly; anything else is refused. Leaving REVIEW_REQUIRED for
NORMAL_MONITORING is a human review: it needs an engineer and a comment. A new event on a component
supersedes that component's open workflow (recorded, not a transition). The workflow tracks state for
monitoring; it sends no alerts.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.audit import record as audit
from app.core.db import Base
from app.core.security import Principal, Role
from app.equipment.lifecycle import EquipmentConflictError, EquipmentNotFoundError, EquipmentStore, _aware
from app.equipment.schemas import (
    MaintenanceEvent,
    MaintenanceEventCreate,
    MaintenanceEventType,
    MaintenanceRecordResult,
    MaintenanceWorkflow,
    MaintenanceWorkflowState,
    WorkflowTransition,
    WorkflowTransitionRequest,
    can_transition,
)

W = MaintenanceWorkflowState
NO_WORKFLOW = {MaintenanceEventType.INSPECTION}
OPEN = {W.MAINTENANCE_EVENT, W.STABILIZATION, W.POST_MAINTENANCE_VALIDATION, W.REVIEW_REQUIRED}


class WorkflowTransitionError(ValueError):
    """The requested transition is not allowed from the workflow's current state."""


class WorkflowPermissionError(PermissionError):
    pass


class MaintenanceEventRecord(Base):
    __tablename__ = "maintenance_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    component_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    lifecycle_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    performed_by: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    new_lifecycle_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_simulated: Mapped[bool] = mapped_column(nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def to_model(self) -> MaintenanceEvent:
        return MaintenanceEvent(
            event_id=self.event_id,
            component_id=self.component_id,
            lifecycle_id=self.lifecycle_id,
            type=MaintenanceEventType(self.type),
            performed_at=_aware(self.performed_at),
            performed_by=self.performed_by,
            notes=self.notes,
            new_lifecycle_id=self.new_lifecycle_id,
            is_simulated=self.is_simulated,
        )


class WorkflowRecord(Base):
    __tablename__ = "maintenance_workflows"

    workflow_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    component_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    lifecycle_id: Mapped[str] = mapped_column(String(80), nullable=False)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transitions: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    is_simulated: Mapped[bool] = mapped_column(nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __mapper_args__ = {"version_id_col": revision}  # concurrent transitions fail instead of overwriting

    def to_model(self) -> MaintenanceWorkflow:
        return MaintenanceWorkflow(
            workflow_id=self.workflow_id,
            component_id=self.component_id,
            lifecycle_id=self.lifecycle_id,
            event_id=self.event_id,
            state=W(self.state),
            started_at=_aware(self.started_at),
            updated_at=_aware(self.updated_at),
            superseded_by=self.superseded_by,
            transitions=[WorkflowTransition.model_validate(t) for t in self.transitions],
            is_simulated=self.is_simulated,
        )


class MaintenanceService:
    def __init__(self, session: Session):
        self.session = session
        self.equipment = EquipmentStore(session)

    # --- events --------------------------------------------------------------------------------

    def events(self, component_id: str) -> list[MaintenanceEvent]:
        self.equipment.component(component_id)
        stmt = select(MaintenanceEventRecord).where(MaintenanceEventRecord.component_id == component_id)
        recs = self.session.scalars(stmt.order_by(MaintenanceEventRecord.performed_at))
        return [r.to_model() for r in recs]

    def record_event(
        self,
        req: MaintenanceEventCreate,
        who: Principal,
        event_id: str | None = None,
        now: datetime | None = None,
    ) -> MaintenanceRecordResult:
        now = now or datetime.now(UTC)
        if req.performed_at > now:
            raise EquipmentConflictError("a maintenance event cannot be in the future")
        sim = self.equipment.is_simulated(req.component_id)
        current = self.equipment.active_record(req.component_id)
        last = self._last_event_time(req.component_id)
        if last is not None and req.performed_at < last:
            raise EquipmentConflictError(
                "events are recorded in time order; this one is earlier than the latest recorded event"
            )
        if req.performed_at < _aware(current.installed_at):  # type: ignore[operator]
            raise EquipmentConflictError("the event is before the current installation")
        eid = event_id or f"ME-{uuid.uuid4().hex[:12]}"
        if self.session.get(MaintenanceEventRecord, eid) is not None:
            raise EquipmentConflictError(f"event '{eid}' already exists")

        touched = [current]
        new_lc = None
        if req.type == MaintenanceEventType.REPLACEMENT:
            old, new_lc = self.equipment.replace(req.component_id, req.performed_at)
            touched = [old, new_lc]
        rec = MaintenanceEventRecord(
            event_id=eid,
            component_id=req.component_id,
            lifecycle_id=current.lifecycle_id,  # the installation the work was done on
            type=req.type.value,
            performed_at=req.performed_at,
            performed_by=who.user_id,
            notes=req.notes,
            new_lifecycle_id=new_lc.lifecycle_id if new_lc else None,
            is_simulated=sim,
            recorded_at=now,
        )
        self.session.add(rec)
        event = rec.to_model()
        audit(
            self.session,
            who,
            "maintenance.event",
            "maintenance_event",
            eid,
            component_id=req.component_id,
            type=req.type.value,
            performed_at=req.performed_at.isoformat(),
            lifecycle_id=current.lifecycle_id,
            new_lifecycle_id=event.new_lifecycle_id,
        )

        workflow, superseded = None, []
        if req.type not in NO_WORKFLOW:
            wid = f"WF-{eid}"
            for open_wf in self._open(req.component_id):
                open_wf.superseded_by, open_wf.updated_at = wid, now
                superseded.append(open_wf.workflow_id)
                audit(
                    self.session,
                    who,
                    "maintenance_workflow.superseded",
                    "maintenance_workflow",
                    open_wf.workflow_id,
                    state=open_wf.state,
                    superseded_by=wid,
                )
            wf = WorkflowRecord(
                workflow_id=wid,
                component_id=req.component_id,
                lifecycle_id=(new_lc or current).lifecycle_id,  # the installation being monitored next
                event_id=eid,
                state=W.MAINTENANCE_EVENT.value,
                started_at=now,
                updated_at=now,
                transitions=[self._transition(None, W.MAINTENANCE_EVENT, now, who, "maintenance recorded")],
                is_simulated=sim,
            )
            self.session.add(wf)
            self.session.flush()
            workflow = wf.to_model()
            audit(
                self.session,
                who,
                "maintenance_workflow.start",
                "maintenance_workflow",
                wid,
                event_id=eid,
                to_state=W.MAINTENANCE_EVENT.value,
            )
        self.session.flush()
        return MaintenanceRecordResult(
            event=event, lifecycles=[r.to_model() for r in touched], workflow=workflow, superseded=superseded
        )

    def _last_event_time(self, component_id: str) -> datetime | None:
        stmt = select(MaintenanceEventRecord.performed_at).where(
            MaintenanceEventRecord.component_id == component_id
        )
        return _aware(self.session.scalar(stmt.order_by(MaintenanceEventRecord.performed_at.desc())))

    # --- workflows -----------------------------------------------------------------------------

    def _open(self, component_id: str) -> list[WorkflowRecord]:
        stmt = select(WorkflowRecord).where(
            WorkflowRecord.component_id == component_id,
            WorkflowRecord.superseded_by.is_(None),
            WorkflowRecord.state.in_([s.value for s in OPEN]),
        )
        return list(self.session.scalars(stmt))

    def workflows(
        self, component_id: str | None = None, open_only: bool = False
    ) -> list[MaintenanceWorkflow]:
        stmt = select(WorkflowRecord).order_by(WorkflowRecord.started_at, WorkflowRecord.workflow_id)
        if component_id:
            stmt = stmt.where(WorkflowRecord.component_id == component_id)
        out = [r.to_model() for r in self.session.scalars(stmt)]
        return [w for w in out if w.superseded_by is None and w.state in OPEN] if open_only else out

    def workflow(self, workflow_id: str) -> MaintenanceWorkflow:
        return self._workflow(workflow_id).to_model()

    def _workflow(self, workflow_id: str) -> WorkflowRecord:
        rec = self.session.get(WorkflowRecord, workflow_id)
        if rec is None:
            raise EquipmentNotFoundError(f"workflow '{workflow_id}' does not exist")
        return rec

    @staticmethod
    def _transition(src: W | None, dst: W, at: datetime, who: Principal, comment: str) -> dict:
        return WorkflowTransition(
            from_state=src, to_state=dst, at=at, by=who.user_id, comment=comment
        ).model_dump(mode="json")

    def transition(
        self, workflow_id: str, req: WorkflowTransitionRequest, who: Principal, now: datetime | None = None
    ) -> MaintenanceWorkflow:
        now = now or datetime.now(UTC)
        rec = self._workflow(workflow_id)
        current = W(rec.state)
        if rec.superseded_by:
            raise WorkflowTransitionError(f"workflow was superseded by {rec.superseded_by}")
        if req.expected_state is not None and req.expected_state != current:
            raise WorkflowTransitionError(f"workflow is in {current.value}, not {req.expected_state.value}")
        if not can_transition(current, req.target):
            raise WorkflowTransitionError(
                f"{current.value} -> {req.target.value} is not an allowed transition"
            )
        if req.target == W.MAINTENANCE_EVENT:
            raise WorkflowTransitionError("a new maintenance cycle starts by recording a maintenance event")
        if current == W.REVIEW_REQUIRED:
            if not who.at_least(Role.ENGINEER):
                raise WorkflowPermissionError("closing a review requires an engineer")
            if not req.comment.strip():
                raise WorkflowTransitionError("closing a review requires a comment with the review outcome")
        rec.state, rec.updated_at = req.target.value, now
        rec.transitions = [
            *rec.transitions,
            self._transition(current, req.target, now, who, req.comment.strip()),
        ]
        audit(
            self.session,
            who,
            "maintenance_workflow.transition",
            "maintenance_workflow",
            workflow_id,
            from_state=current.value,
            to_state=req.target.value,
            comment=req.comment.strip(),
        )
        self.session.flush()
        return rec.to_model()
