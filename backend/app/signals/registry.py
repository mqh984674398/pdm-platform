"""Versioned signal configuration (L2-01..L2-05, SEC-02).

The configuration is stored as immutable snapshots: every change, whether one item or a whole
device from the Studio, writes a new version with the full content, its hash, and an audit row in
the same transaction. Old versions are never modified, so any version can be inspected or restored.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import JSON, DateTime, Integer, String, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.audit import record as audit
from app.core.db import Base
from app.core.security import Principal
from app.signals.schemas import (
    DeviceConfigChange,
    SignalConfig,
    SignalConfigState,
    SignalConfigVersion,
    SignalConfigVersionDetail,
)

# collection name -> id field of its items
COLLECTIONS = {
    "signals": "signal_id",
    "mappings": "signal_id",
    "groups": "group_id",
    "visualizations": "template_id",
}


class ConfigConflictError(ValueError):
    """The change would break the configuration's invariants, or it is based on an old version."""


class ConfigNotFoundError(LookupError):
    pass


class SignalConfigRecord(Base):
    __tablename__ = "signal_config_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    comment: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    content_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    def to_version(self) -> SignalConfigVersion:
        at = self.created_at if self.created_at.tzinfo else self.created_at.replace(tzinfo=UTC)
        return SignalConfigVersion(
            version=self.version,
            created_at=at,
            created_by=self.created_by,
            comment=self.comment,
            content_hash=self.content_hash,
        )

    def to_detail(self) -> SignalConfigVersionDetail:
        return SignalConfigVersionDetail(
            **self.to_version().model_dump(), content=SignalConfig.model_validate(self.content)
        )


def content_hash(content: SignalConfig) -> str:
    canonical = json.dumps(content.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build(**parts: Any) -> SignalConfig:
    try:
        return SignalConfig(**parts)
    except ValidationError as exc:
        raise ConfigConflictError(
            "; ".join(e["msg"].removeprefix("Value error, ") for e in exc.errors())
        ) from exc


class SignalConfigStore:
    def __init__(self, session: Session):
        self.session = session

    # --- reads ---------------------------------------------------------------------------------

    def _latest(self) -> SignalConfigRecord | None:
        return self.session.scalar(select(SignalConfigRecord).order_by(SignalConfigRecord.version.desc()))

    def current(self) -> SignalConfigState:
        rec = self._latest()
        if rec is None:
            return SignalConfigState(version=None, content=SignalConfig())
        return SignalConfigState(version=rec.to_version(), content=SignalConfig.model_validate(rec.content))

    def versions(self) -> list[SignalConfigVersion]:
        recs = self.session.scalars(select(SignalConfigRecord).order_by(SignalConfigRecord.version.desc()))
        return [r.to_version() for r in recs]

    def get(self, version: int) -> SignalConfigVersionDetail:
        rec = self.session.scalar(select(SignalConfigRecord).where(SignalConfigRecord.version == version))
        if rec is None:
            raise ConfigNotFoundError(f"signal configuration version {version} does not exist")
        return rec.to_detail()

    # --- changes -------------------------------------------------------------------------------

    def put_item(
        self,
        collection: str,
        item: BaseModel,
        who: Principal,
        comment: str = "",
        base_version: int | None = None,
    ) -> SignalConfigVersion:
        key = COLLECTIONS[collection]
        item_id = getattr(item, key)

        def change(parts: dict[str, list]) -> str:
            items = parts[collection]
            existing = [i for i, x in enumerate(items) if getattr(x, key) == item_id]
            if existing:
                items[existing[0]] = item
                return "update"
            items.append(item)
            return "create"

        return self._apply(change, who, comment, base_version, collection=collection, item_id=item_id)

    def delete_item(
        self,
        collection: str,
        item_id: str,
        who: Principal,
        comment: str = "",
        base_version: int | None = None,
    ) -> SignalConfigVersion:
        key = COLLECTIONS[collection]

        def change(parts: dict[str, list]) -> str:
            before = len(parts[collection])
            parts[collection] = [x for x in parts[collection] if getattr(x, key) != item_id]
            if len(parts[collection]) == before:
                raise ConfigNotFoundError(f"{collection} item '{item_id}' does not exist")
            return "delete"

        return self._apply(change, who, comment, base_version, collection=collection, item_id=item_id)

    def replace_device(
        self, data_source_id: str, device_id: str, change: DeviceConfigChange, who: Principal
    ) -> SignalConfigVersion:
        foreign = [
            m.signal_id
            for m in change.mappings
            if (m.data_source_id, m.device_id) != (data_source_id, device_id)
        ]
        if foreign:
            raise ConfigConflictError(f"mappings for other devices in this change: {', '.join(foreign)}")

        def apply(parts: dict[str, list]) -> str:
            old = {
                m.signal_id
                for m in parts["mappings"]
                if (m.data_source_id, m.device_id) == (data_source_id, device_id)
            }

            def owned(item) -> bool:  # groups/charts made only of this device's signals
                return bool(item.signal_ids) and set(item.signal_ids) <= old

            parts["mappings"] = [m for m in parts["mappings"] if m.signal_id not in old] + change.mappings
            parts["signals"] = [s for s in parts["signals"] if s.signal_id not in old] + change.signals
            parts["groups"] = [g for g in parts["groups"] if not owned(g)] + change.groups
            parts["visualizations"] = [
                v for v in parts["visualizations"] if not owned(v)
            ] + change.visualizations
            return "replace_device"

        return self._apply(
            apply,
            who,
            change.comment,
            change.base_version,
            data_source_id=data_source_id,
            device_id=device_id,
        )

    def _apply(
        self,
        change: Callable[[dict[str, list]], str],
        who: Principal,
        comment: str,
        base_version: int | None,
        **details: Any,
    ) -> SignalConfigVersion:
        latest = self._latest()
        current_version = latest.version if latest else 0
        if base_version is not None and base_version != current_version:
            raise ConfigConflictError(
                f"the configuration changed since version {base_version} "
                f"(now version {current_version}); reload and retry"
            )
        content = SignalConfig.model_validate(latest.content) if latest else SignalConfig()
        parts = {name: list(getattr(content, name)) for name in COLLECTIONS}
        action = change(parts)
        new = _build(**parts)
        digest = content_hash(new)
        if latest and digest == latest.content_hash:
            raise ConfigConflictError("no changes")
        rec = SignalConfigRecord(
            version=current_version + 1,
            created_at=datetime.now(UTC),
            created_by=who.user_id,
            comment=comment.strip(),
            content_hash=digest,
            content=new.model_dump(mode="json"),
        )
        try:
            with self.session.begin_nested():
                self.session.add(rec)
        except IntegrityError as exc:  # another writer saved the same version number first
            raise ConfigConflictError("the configuration was changed concurrently; reload and retry") from exc
        audit(
            self.session,
            who,
            f"signal_config.{action}",
            "signal_config",
            str(rec.version),
            previous_version=current_version,
            content_hash=digest,
            comment=rec.comment,
            **details,
        )
        return rec.to_version()
