"""How machines are laid out on the equipment overview (D-054): their order within a workshop page and an
optional background picture. Presentation only; administrators change it and every change is audited."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field
from sqlalchemy import Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.audit import record as audit
from app.core.db import Base
from app.core.schemas import ContractModel
from app.core.security import Principal, Role
from app.equipment.lifecycle import EquipmentNotFoundError, MachineRecord
from app.equipment.plant import PlantPermissionError

MAX_IMAGE_CHARS = 700_000  # about 500 KB of image; the browser scales pictures down before sending


class MachineLayoutRecord(Base):
    __tablename__ = "machine_layout"

    machine_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sort: Mapped[int | None] = mapped_column(Integer, nullable=True)
    background: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)


class MachineLayout(ContractModel):
    machine_id: str
    sort: int | None = None
    background: str | None = Field(default=None, description="A data: URL of the background picture")


class OrderChange(ContractModel):
    machine_ids: list[str] = Field(min_length=1, max_length=500)


class BackgroundChange(ContractModel):
    image: str | None = Field(
        default=None,
        max_length=MAX_IMAGE_CHARS,
        pattern=r"^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$",
        description="A PNG, JPEG or WebP picture as a data: URL, or null to clear it",
    )


class LayoutStore:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _admin(who: Principal) -> None:
        if who.role != Role.ADMIN:
            raise PlantPermissionError("only an administrator may change the equipment layout")

    def _rec(self, machine_id: str, who: Principal) -> MachineLayoutRecord:
        if self.session.get(MachineRecord, machine_id) is None:
            raise EquipmentNotFoundError(f"machine {machine_id} not found")
        rec = self.session.get(MachineLayoutRecord, machine_id)
        if rec is None:
            rec = MachineLayoutRecord(
                machine_id=machine_id, updated_by=who.user_id, updated_at=datetime.now(UTC)
            )
            self.session.add(rec)
        rec.updated_by, rec.updated_at = who.user_id, datetime.now(UTC)
        return rec

    def all(self) -> list[MachineLayout]:
        known = set(self.session.scalars(select(MachineRecord.machine_id)))
        return [
            MachineLayout(machine_id=r.machine_id, sort=r.sort, background=r.background)
            for r in self.session.scalars(
                select(MachineLayoutRecord).order_by(MachineLayoutRecord.machine_id)
            )
            if r.machine_id in known
        ]

    def set_order(self, body: OrderChange, who: Principal) -> None:
        self._admin(who)
        for i, mid in enumerate(dict.fromkeys(body.machine_ids)):
            self._rec(mid, who).sort = i
        audit(self.session, who, "plant.layout_order", "machine", body.machine_ids[0], after=body.machine_ids)

    def set_background(self, machine_id: str, body: BackgroundChange, who: Principal) -> None:
        self._admin(who)
        self._rec(machine_id, who).background = body.image
        audit(self.session, who, "plant.layout_background", "machine", machine_id, after=bool(body.image))
