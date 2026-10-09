"""Rule fixtures: stored features and a verified reference for the first healthy week after the
regime reference (96–168 h), the same for every scenario."""

from __future__ import annotations

from ..baselines.conftest import client, db, factory, store, verify  # noqa: F401
from ..equipment.conftest import GOLDEN, scenario
from ..features.conftest import components, extraction

REF = (96.0, 168.0)


def references(db, sid: str) -> dict:  # noqa: F811
    """Verified reference per component of the scenario, through the audited verification."""
    store(db, sid)
    out = {}
    for cid in components(sid):
        vs = [v for v in extraction(sid).vectors if v.component_id == cid]
        if vs:
            out[cid] = verify(db, sid, cid, vs[0].lifecycle_id, vs[0].feature_ref, *REF)
    return out


def after_reference(sid: str, cid: str):
    end = scenario(sid).t0.timestamp() + REF[1] * 3600
    return [v for v in extraction(sid).vectors if v.component_id == cid and v.window.start.timestamp() >= end]


__all__ = ["GOLDEN", "after_reference", "client", "db", "factory", "references", "scenario"]
