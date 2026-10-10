"""Baseline fixtures: an application database with the scenario's feature vectors stored."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.core.audit  # noqa: F401  (registers tables)
import app.equipment.lifecycle  # noqa: F401
import app.equipment.maintenance  # noqa: F401
import app.equipment.maintenance_impact.service  # noqa: F401
import app.monitoring.alarms.service  # noqa: F401
import app.monitoring.baselines.verified  # noqa: F401
import app.monitoring.features.store  # noqa: F401
import app.monitoring.rules.settings  # noqa: F401
from app.core.db import Base, get_session
from app.core.schemas import TimeWindow
from app.core.security import Principal, Role
from app.datasource.query_service.sources import DataSourceRegistry
from app.equipment.schemas import MaintenanceEvent, MaintenanceEventType
from app.main import create_app
from app.monitoring.baselines.verified import BaselineService
from app.monitoring.features.store import FeatureStore
from app.monitoring.schemas import Baseline, BaselineVerification

from ..datasource.conftest import PG_URL
from ..equipment.conftest import scenario
from ..features.conftest import extraction
from ..query_service.conftest import Client

ENGINEER = Principal(user_id="eng1", role=Role.ENGINEER)


@pytest.fixture
def factory(tmp_path):
    engine = create_engine(PG_URL or f"sqlite:///{tmp_path / 'app.db'}")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def db(factory):
    with factory() as s:
        yield s


@pytest.fixture
def client(factory):
    def session():
        with factory() as s:
            yield s

    application = create_app(sources=DataSourceRegistry())
    application.dependency_overrides[get_session] = session
    return Client(application)


def store(db: Session, *sids: str) -> None:
    fs = FeatureStore(db)
    fs.register_all()
    for sid in sids:
        fs.save(extraction(sid).vectors)
    db.commit()


def window(sid: str, a: float, b: float) -> TimeWindow:
    return scenario(sid).window(a, b)


def verify(db: Session, sid: str, cid: str, lc: str, ref: str, a: float, b: float) -> Baseline:
    req = BaselineVerification(
        component_id=cid,
        lifecycle_id=lc,
        feature_ref=ref,
        window=window(sid, a, b),
        comment="known good period",
    )
    out = BaselineService(db).verify(req, ENGINEER)
    db.commit()
    return out


def sim_events(sid: str) -> list[MaintenanceEvent]:
    sc = scenario(sid)
    out = []
    for i, m in enumerate(sc.cfg.get("maintenance", [])):
        cid = m["component_id"]
        lcs = sorted(lc["lifecycle_id"] for lc in sc.topology["lifecycles"] if lc["component_id"] == cid)
        replacement = m["type"] == "REPLACEMENT"
        out.append(
            MaintenanceEvent(
                event_id=f"sim-{i}",
                component_id=cid,
                lifecycle_id=lcs[0] if replacement else lcs[-1],
                type=MaintenanceEventType(m["type"]),
                performed_at=sc.t0 + timedelta(hours=m["at_h"]),
                performed_by=m["performed_by"],
                new_lifecycle_id=lcs[1] if replacement else None,
                is_simulated=True,
            )
        )
    return out
