"""Champion/challenger deployment registry (T026, OPT-04, OPT-06, SEC-02).

A generic, versioned store of deployable payloads per ``kind`` (for example ``decision-config`` or
``component-model:BALL_SCREW``). Payloads are opaque JSON here; higher layers interpret them.

- ``propose`` stores a CANDIDATE with its evaluation. The evaluation must say whether the replay and
  Golden Case gates passed (``gate_passed``) and against which champion it was measured
  (``baseline_version``).
- ``promote`` needs an administrator, a comment, a passed gate measured against the current champion,
  and records the decision in the audit log. The old champion is kept as RETIRED.
- ``rollback`` restores the champion's predecessor in one audited action (engineer or above).
- Nothing is ever deleted, so every previous payload stays available for rollback.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import AwareDatetime
from sqlalchemy import JSON, DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.audit import record as audit
from app.core.db import Base
from app.core.schemas import ContractModel
from app.core.security import Principal, Role

RANK = {Role.VIEWER: 0, Role.MAINTENANCE: 1, Role.ENGINEER: 2, Role.ADMIN: 3}


class DeploymentStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    CHAMPION = "CHAMPION"
    RETIRED = "RETIRED"
    REJECTED = "REJECTED"


class RegistryError(ValueError):
    pass


class RegistryNotFoundError(KeyError):
    pass


class RegistryPermissionError(PermissionError):
    pass


class DeploymentVersion(ContractModel):
    version_id: str
    kind: str
    number: int
    status: DeploymentStatus
    payload: dict[str, Any]
    evaluation: dict[str, Any] | None
    created_by: str
    created_at: AwareDatetime
    decided_by: str | None
    decided_at: AwareDatetime | None
    comment: str
    previous_version_id: str | None
    is_simulated: bool


class DeploymentRecord(Base):
    __tablename__ = "deployment_versions"

    version_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    evaluation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comment: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    previous_version_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    is_simulated: Mapped[bool] = mapped_column(nullable=False)

    def to_model(self) -> DeploymentVersion:
        def aware(t: datetime | None) -> datetime | None:
            return t if t is None or t.tzinfo else t.replace(tzinfo=UTC)

        return DeploymentVersion(
            version_id=self.version_id,
            kind=self.kind,
            number=self.number,
            status=DeploymentStatus(self.status),
            payload=self.payload,
            evaluation=self.evaluation,
            created_by=self.created_by,
            created_at=aware(self.created_at),
            decided_by=self.decided_by,
            decided_at=aware(self.decided_at),
            comment=self.comment,
            previous_version_id=self.previous_version_id,
            is_simulated=self.is_simulated,
        )


def _need(who: Principal, role: Role, what: str) -> None:
    if RANK[who.role] < RANK[role]:
        raise RegistryPermissionError(f"{what} requires the {role.value} role")


class DeploymentRegistry:
    def __init__(self, session: Session, kind: str):
        self.session, self.kind = session, kind

    def _rows(self) -> list[DeploymentRecord]:
        stmt = (
            select(DeploymentRecord)
            .where(DeploymentRecord.kind == self.kind)
            .order_by(DeploymentRecord.number)
        )
        return list(self.session.scalars(stmt))

    def _row(self, version_id: str) -> DeploymentRecord:
        row = self.session.get(DeploymentRecord, version_id)
        if row is None or row.kind != self.kind:
            raise RegistryNotFoundError(f"unknown {self.kind} version {version_id}")
        return row

    def history(self) -> list[DeploymentVersion]:
        return [r.to_model() for r in self._rows()]

    def champion(self) -> DeploymentVersion | None:
        row = next((r for r in self._rows() if r.status == DeploymentStatus.CHAMPION), None)
        return row.to_model() if row else None

    def get(self, version_id: str) -> DeploymentVersion:
        return self._row(version_id).to_model()

    def _add(
        self,
        payload: dict,
        evaluation: dict | None,
        who: Principal,
        comment: str,
        status: str,
        previous: str | None,
        simulated: bool,
    ) -> DeploymentRecord:
        number = len(self._rows()) + 1
        row = DeploymentRecord(
            version_id=f"{self.kind}.v{number}",
            kind=self.kind,
            number=number,
            status=status,
            payload=payload,
            evaluation=evaluation,
            created_by=who.user_id,
            created_at=datetime.now(UTC),
            comment=comment,
            previous_version_id=previous,
            is_simulated=simulated,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def seed(self, payload: dict, who: Principal, simulated: bool) -> DeploymentVersion:
        """Record the configuration in use as the first champion; it is the baseline, so no evaluation."""
        if self._rows():
            raise RegistryError(f"{self.kind} already has versions")
        row = self._add(
            payload, None, who, "initial configuration", DeploymentStatus.CHAMPION, None, simulated
        )
        row.decided_by, row.decided_at = who.user_id, row.created_at
        audit(self.session, who, "registry.seed", self.kind, row.version_id)
        self.session.commit()
        return row.to_model()

    def propose(
        self, payload: dict, evaluation: dict, who: Principal, comment: str, simulated: bool
    ) -> DeploymentVersion:
        _need(who, Role.ENGINEER, "proposing a candidate")
        if "gate_passed" not in evaluation or "baseline_version" not in evaluation:
            raise RegistryError("a candidate needs an evaluation with gate_passed and baseline_version")
        row = self._add(payload, evaluation, who, comment, DeploymentStatus.CANDIDATE, None, simulated)
        audit(
            self.session,
            who,
            "registry.propose",
            self.kind,
            row.version_id,
            gate_passed=evaluation["gate_passed"],
        )
        self.session.commit()
        return row.to_model()

    def promote(self, version_id: str, who: Principal, comment: str) -> DeploymentVersion:
        _need(who, Role.ADMIN, "promoting a candidate")
        if not comment.strip():
            raise RegistryError("a promotion needs a comment")
        row = self._row(version_id)
        if row.status != DeploymentStatus.CANDIDATE:
            raise RegistryError(f"{version_id} is {row.status}, not a candidate")
        ev = row.evaluation or {}
        if ev.get("gate_passed") is not True:
            raise RegistryError(f"{version_id} did not pass the replay and Golden Case gates")
        current = next((r for r in self._rows() if r.status == DeploymentStatus.CHAMPION), None)
        if current is not None and ev.get("baseline_version") != current.version_id:
            raise RegistryError(
                f"{version_id} was evaluated against {ev.get('baseline_version')}, not the "
                f"current champion {current.version_id}; evaluate it again"
            )
        now = datetime.now(UTC)
        if current is not None:
            current.status = DeploymentStatus.RETIRED
        row.status, row.decided_by, row.decided_at = DeploymentStatus.CHAMPION, who.user_id, now
        row.previous_version_id = current.version_id if current else None
        row.comment = f"{row.comment}\n[promoted] {comment}".strip()
        audit(
            self.session,
            who,
            "registry.promote",
            self.kind,
            version_id,
            previous=row.previous_version_id,
            comment=comment,
        )
        self.session.commit()
        return row.to_model()

    def reject(self, version_id: str, who: Principal, comment: str) -> DeploymentVersion:
        _need(who, Role.ENGINEER, "rejecting a candidate")
        row = self._row(version_id)
        if row.status != DeploymentStatus.CANDIDATE:
            raise RegistryError(f"{version_id} is {row.status}, not a candidate")
        row.status, row.decided_by, row.decided_at = DeploymentStatus.REJECTED, who.user_id, datetime.now(UTC)
        row.comment = f"{row.comment}\n[rejected] {comment}".strip()
        audit(self.session, who, "registry.reject", self.kind, version_id, comment=comment)
        self.session.commit()
        return row.to_model()

    def rollback(self, who: Principal, comment: str) -> DeploymentVersion:
        """Make the current champion's predecessor champion again, as a new version with the same payload."""
        _need(who, Role.ENGINEER, "rolling back")
        if not comment.strip():
            raise RegistryError("a rollback needs a comment")
        current = next((r for r in self._rows() if r.status == DeploymentStatus.CHAMPION), None)
        if current is None or current.previous_version_id is None:
            raise RegistryError(f"{self.kind} has no previous champion to roll back to")
        prev = self._row(current.previous_version_id)
        current.status = DeploymentStatus.RETIRED
        row = self._add(
            prev.payload,
            prev.evaluation,
            who,
            f"rollback to {prev.version_id}: {comment}",
            DeploymentStatus.CHAMPION,
            current.version_id,
            prev.is_simulated,
        )
        row.decided_by, row.decided_at = who.user_id, row.created_at
        audit(
            self.session,
            who,
            "registry.rollback",
            self.kind,
            row.version_id,
            restored=prev.version_id,
            replaced=current.version_id,
            comment=comment,
        )
        self.session.commit()
        return row.to_model()
