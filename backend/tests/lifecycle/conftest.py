"""Lifecycle API fixtures. The application database is PostgreSQL when PDM_TEST_PG_URL is set."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.core.audit  # noqa: F401  (registers tables)
import app.datasource.query_service.registry  # noqa: F401
import app.equipment.lifecycle  # noqa: F401
import app.equipment.maintenance  # noqa: F401
import app.monitoring.baselines.verified  # noqa: F401
import app.monitoring.features.store  # noqa: F401
import app.signals.registry  # noqa: F401
from app.core.db import Base, get_session
from app.datasource.query_service.sources import DataSourceRegistry
from app.main import create_app

from ..datasource.conftest import PG_URL
from ..equipment.conftest import scenario
from ..query_service.conftest import Client


@pytest.fixture
def client(tmp_path):
    engine = create_engine(PG_URL or f"sqlite:///{tmp_path / 'app.db'}")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    def session():
        with factory() as s:
            yield s

    application = create_app(sources=DataSourceRegistry())
    application.dependency_overrides[get_session] = session
    yield Client(application)
    engine.dispose()


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def seed(client: Client, sid: str) -> dict:
    """Machine and components of a scenario, each installed at the scenario start (LC1)."""
    sc = scenario(sid)
    topo = sc.topology
    for m in topo["machines"]:
        assert client.put(f"/api/machines/{m['machine_id']}", m, role="engineer").status_code == 200
    for c in topo["components"]:
        assert client.put(f"/api/components/{c['component_id']}", c, role="engineer").status_code == 200
        r = client.post(
            f"/api/components/{c['component_id']}/lifecycles", {"installed_at": iso(sc.t0)}, role="engineer"
        )
        assert r.status_code == 201, r.text
    return topo


def sim_maintenance(sid: str) -> list[dict]:
    sc = scenario(sid)
    return [
        {**m, "performed_at": iso(sc.t0 + timedelta(hours=m["at_h"]))} for m in sc.cfg.get("maintenance", [])
    ]


def sim_events(sid: str) -> list[dict]:
    return json.loads((scenario(sid).dir / "maintenance_events.json").read_text(encoding="utf-8"))


def record(
    client: Client, component_id: str, type_: str, at: str, role: str = "maintenance", notes: str = ""
):
    body = {"component_id": component_id, "type": type_, "performed_at": at, "notes": notes}
    return client.post("/api/maintenance-events", body, role=role)
