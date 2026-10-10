"""Feature fixtures: simulated scenarios with a regime catalog learned before the extraction window."""

from __future__ import annotations

from datetime import datetime
from functools import cache

from app.equipment.regimes import learn_catalog
from app.equipment.schemas import ComponentType, RegimeCatalog
from app.monitoring.features.extract import extract_features
from app.monitoring.schemas import FeatureExtraction

from ..equipment.conftest import scenario, series

REFERENCE_H = 96.0


def components(sid: str) -> dict[str, ComponentType]:
    return {c["component_id"]: ComponentType(c["type"]) for c in scenario(sid).topology["components"]}


def lifecycles(sid: str) -> dict[str, list[tuple[str, datetime, datetime | None]]]:
    out: dict[str, list[tuple[str, datetime, datetime | None]]] = {}
    for lc in scenario(sid).topology["lifecycles"]:
        a = datetime.fromisoformat(lc["installed_at"].replace("Z", "+00:00"))
        b = datetime.fromisoformat(lc["retired_at"].replace("Z", "+00:00")) if lc["retired_at"] else None
        out.setdefault(lc["component_id"], []).append((lc["lifecycle_id"], a, b))
    return out


@cache
def catalog(sid: str) -> RegimeCatalog:
    sc = scenario(sid)
    return learn_catalog(series(sid), sc.machine, sc.window(0, REFERENCE_H), f"{sid}-ref")


@cache
def extraction(sid: str) -> FeatureExtraction:
    sc = scenario(sid)
    return extract_features(
        series(sid),
        sc.window(REFERENCE_H, sc.hours),
        components(sid),
        lifecycles(sid),
        catalog(sid),
        sc.maintenance(),
    )
