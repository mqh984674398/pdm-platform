"""Maintenance impact fixtures: regime catalog from 0–96 h, events recorded through the API."""

from __future__ import annotations

from functools import cache

from app.equipment.regimes import learn_catalog
from app.equipment.schemas import RegimeCatalog

from ..baselines.conftest import client, db, factory  # noqa: F401
from ..equipment.conftest import GOLDEN, scenario, series

__all__ = ["GOLDEN", "catalog", "client", "db", "factory", "scenario", "series"]


@cache
def catalog(sid: str) -> RegimeCatalog:
    sc = scenario(sid)
    return learn_catalog(series(sid), sc.machine, sc.window(0, 96), f"{sid}-ref")
