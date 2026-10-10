"""Drive a maintenance workflow from the impact analysis (L3-07), audited.

``advance`` moves a workflow as far as time and data allow:
MAINTENANCE_EVENT -> STABILIZATION at once; -> POST_MAINTENANCE_VALIDATION when the stabilization
period has passed; then, once ``validation_hours`` of data follow, the analysis decides:
IMPROVED or NO_CHANGE -> NORMAL_MONITORING; PARTIAL or DETERIORATED -> REVIEW_REQUIRED. While the
outcome is UNKNOWN the workflow keeps waiting with a longer comparison period; after
``max_validation_hours`` it goes to REVIEW_REQUIRED so a person decides. Leaving REVIEW_REQUIRED stays
a human step. The latest analysis of each workflow is stored. Nothing here sends an alert.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.audit import record as audit
from app.core.db import Base
from app.core.security import Principal, Role
from app.equipment.cycles import CycleSignal
from app.equipment.lifecycle import _aware
from app.equipment.maintenance import MaintenanceEventRecord, MaintenanceService
from app.equipment.maintenance_impact.analysis import analyze_impact
from app.equipment.schemas import (
    ImpactConfig,
    ImpactOutcome,
    MaintenanceImpact,
    MaintenanceWorkflow,
    RegimeCatalog,
    WorkflowTransitionRequest,
)
from app.equipment.schemas import MaintenanceWorkflowState as W
from app.equipment.state import Series

SYSTEM = Principal(user_id="system:maintenance-impact", role=Role.MAINTENANCE)
TO_STATE = {
    ImpactOutcome.IMPROVED: W.NORMAL_MONITORING,
    ImpactOutcome.NO_CHANGE: W.NORMAL_MONITORING,
    ImpactOutcome.PARTIAL: W.REVIEW_REQUIRED,
    ImpactOutcome.DETERIORATED: W.REVIEW_REQUIRED,
}


class ImpactRecord(Base):
    __tablename__ = "maintenance_impacts"

    workflow_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ImpactService:
    def __init__(self, session: Session):
        self.session = session
        self.maintenance = MaintenanceService(session)

    def impact(self, workflow_id: str) -> MaintenanceImpact | None:
        rec = self.session.get(ImpactRecord, workflow_id)
        return MaintenanceImpact.model_validate(rec.result) if rec else None

    def _move(self, wf: MaintenanceWorkflow, target: W, at: datetime, comment: str) -> MaintenanceWorkflow:
        req = WorkflowTransitionRequest(target=target, expected_state=wf.state, comment=comment)
        return self.maintenance.transition(wf.workflow_id, req, SYSTEM, now=at)

    def advance(
        self,
        workflow_id: str,
        series: Sequence[Series],
        catalog: RegimeCatalog,
        now: datetime | None = None,
        config: ImpactConfig | None = None,
        cycle_config: Mapping[str, CycleSignal] | None = None,
    ) -> MaintenanceWorkflow:
        cfg = config or ImpactConfig()
        now = now or datetime.now(UTC)
        wf = self.maintenance.workflow(workflow_id)
        if wf.superseded_by:
            return wf
        event = self.session.get(MaintenanceEventRecord, wf.event_id)
        at = _aware(event.performed_at)
        hours = (now - at).total_seconds() / 3600
        if wf.state == W.MAINTENANCE_EVENT:
            wf = self._move(wf, W.STABILIZATION, now, "stabilization started")
        if wf.state == W.STABILIZATION and hours >= cfg.stabilization_hours:
            wf = self._move(wf, W.POST_MAINTENANCE_VALIDATION, now, "stabilization period passed")
        waited = hours - cfg.stabilization_hours
        if wf.state != W.POST_MAINTENANCE_VALIDATION or waited < cfg.validation_hours:
            return wf
        post = min(waited, cfg.max_validation_hours)
        result = analyze_impact(series, wf.component_id, at, catalog, cfg, cycle_config, post_hours=post)
        rec = self.session.get(ImpactRecord, workflow_id)
        payload = result.model_dump(mode="json")
        if rec is None:
            self.session.add(
                ImpactRecord(
                    workflow_id=workflow_id, outcome=result.outcome.value, result=payload, analyzed_at=now
                )
            )
        else:
            rec.outcome, rec.result, rec.analyzed_at = result.outcome.value, payload, now
        audit(self.session, SYSTEM, "maintenance_impact.analyze", "maintenance_workflow", workflow_id,
              outcome=result.outcome.value, post_hours=post, catalog_id=catalog.catalog_id,
              changes={f.feature_id: f.change for f in result.features})  # fmt: skip
        target = TO_STATE.get(result.outcome)
        if target is None and waited >= cfg.max_validation_hours:
            target = W.REVIEW_REQUIRED
        if target is not None:
            wf = self._move(wf, target, now, f"{result.outcome.value}: {result.reason.en}")
        self.session.flush()
        return wf
