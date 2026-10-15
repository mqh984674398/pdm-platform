"""Standard interface for custom algorithms (D-046).

A plugin declares an explicit input/output contract and a semantic version; a version is immutable once
registered. Registration runs the plugin once on a sample input and refuses it when the output does not
match its contract. Plugins are registered by code on the server, never uploaded through the API.
The decision engine does not consume plugin evidence yet, so a plugin stage compiles as not taking part.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from pydantic import Field

from app.core.schemas import ContractModel, LocalizedText
from app.decision.schemas import EvidenceType, HealthState
from app.signals.schemas import PhysicalQuantity

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
ID = re.compile(r"^[a-z][a-z0-9-]{1,40}$")


class PluginError(ValueError):
    pass


class PluginSpec(ContractModel):
    plugin_id: str
    version: str
    name: LocalizedText
    evidence_type: EvidenceType
    input_quantities: list[PhysicalQuantity] = Field(min_length=1)
    needs_labels: bool = False
    description: LocalizedText

    @property
    def ref(self) -> str:
        return f"plugin:{self.plugin_id}@{self.version}"


class PluginEvidence(ContractModel):
    """What a plugin returns for one window: a value, its threshold and the severity it proposes."""

    raw_value: float
    threshold: float | None = None
    proposed_severity: HealthState | None = None
    applicable: bool = True
    reason: LocalizedText


PluginFn = Callable[[dict[str, list[float]]], PluginEvidence]
PLUGINS: dict[str, tuple[PluginSpec, PluginFn]] = {}


def register_plugin(spec: PluginSpec, fn: PluginFn, sample: dict[str, list[float]]) -> None:
    if not ID.match(spec.plugin_id) or not SEMVER.match(spec.version):
        raise PluginError("plugin_id must be a lower-case identifier and version must be x.y.z")
    if spec.evidence_type in (EvidenceType.SAFETY, EvidenceType.CONTEXT):
        raise PluginError("a plugin cannot produce safety or context evidence")
    if spec.ref in PLUGINS:
        raise PluginError(f"{spec.ref} already exists; versions are immutable")
    missing = [q.value for q in spec.input_quantities if q.value not in sample]
    if missing:
        raise PluginError(f"the sample input lacks declared quantities: {', '.join(missing)}")
    try:
        out: Any = fn(sample)
        PluginEvidence.model_validate(out.model_dump() if isinstance(out, PluginEvidence) else out)
    except Exception as exc:  # noqa: BLE001  (any failure means the contract is not met)
        raise PluginError(f"the plugin did not return a valid PluginEvidence: {exc}") from exc
    if out.proposed_severity in (HealthState.WARNING, HealthState.CRITICAL):
        raise PluginError("a plugin can propose at most WATCH; only rules decide higher severities")
    PLUGINS[spec.ref] = (spec, fn)


def plugin_specs() -> list[PluginSpec]:
    return [s for s, _ in PLUGINS.values()]
