"""Versioned model registry on disk (T022 AC3).

Each model is stored as ``<model_id>.pkl`` next to ``index.json``. The index records the model id
(``family@version``), kind, component type, feature schema reference and feature order, the label
definition, training scenarios, metrics, seed and the artifact's SHA-256. A model is loaded only if
its artifact still matches the recorded hash, because unpickling runs code. Versions are immutable.
"""

from __future__ import annotations

import hashlib
import json
import pickle
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import AwareDatetime, Field

from app.core.schemas import ContractModel
from app.equipment.schemas import ComponentType


class ModelRecord(ContractModel):
    model_id: str = Field(pattern=r"^[a-z0-9_-]+@\d+\.\d+\.\d+$")
    kind: str
    component_type: ComponentType
    feature_ref: str
    features: list[str] = Field(min_length=1)
    label_definition: str
    training_scenarios: list[str]
    params: dict[str, Any]
    seed: int
    metrics: dict[str, Any]
    is_simulated: bool
    created_at: AwareDatetime
    sha256: str = ""


class ModelRegistryError(ValueError):
    pass


class ModelRegistry:
    def __init__(self, directory: Path):
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.dir / "index.json"

    def records(self) -> list[ModelRecord]:
        if not self.index_path.exists():
            return []
        return [
            ModelRecord.model_validate(r) for r in json.loads(self.index_path.read_text(encoding="utf-8"))
        ]

    def get(self, model_id: str) -> ModelRecord:
        rec = next((r for r in self.records() if r.model_id == model_id), None)
        if rec is None:
            raise ModelRegistryError(f"unknown model {model_id}")
        return rec

    def save(self, model: Any, record: ModelRecord) -> ModelRecord:
        if any(r.model_id == record.model_id for r in self.records()):
            raise ModelRegistryError(f"{record.model_id} already exists; versions are immutable")
        blob = pickle.dumps(model, protocol=5)
        record = record.model_copy(update={"sha256": hashlib.sha256(blob).hexdigest()})
        (self.dir / f"{record.model_id}.pkl").write_bytes(blob)
        rows = [r.model_dump(mode="json") for r in self.records()] + [record.model_dump(mode="json")]
        self.index_path.write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
        return record

    def load(self, model_id: str) -> tuple[Any, ModelRecord]:
        rec = self.get(model_id)
        blob = (self.dir / f"{model_id}.pkl").read_bytes()
        if hashlib.sha256(blob).hexdigest() != rec.sha256:
            raise ModelRegistryError(
                f"{model_id}: artifact does not match its recorded hash; refusing to load"
            )
        return pickle.loads(blob), rec  # noqa: S301  (hash-verified artifact written by this registry)


def stamp() -> datetime:
    return datetime.now(UTC)
