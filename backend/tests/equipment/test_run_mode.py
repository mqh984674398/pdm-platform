"""D-053: simulation and production are separate; only an administrator switches; lists follow the mode."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.main  # noqa: F401  (registers tables)
from app.core.db import Base, get_session
from app.datasource.query_service.sources import DataSourceRegistry
from app.main import create_app

from .test_plant import L, build, h


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    def session():
        with factory() as s:
            yield s

    application = create_app(sources=DataSourceRegistry())
    application.dependency_overrides[get_session] = session
    return TestClient(application)


def put_sim_machine(c):
    body = {"machine_id": "SIM01", "name": L("仿真机", "Sim machine"), "is_simulated": True}
    assert c.put("/api/machines/SIM01", json=body, headers=h("engineer")).status_code == 200


def ids(c, role="viewer"):
    return sorted(m["machine_id"] for m in c.get("/api/machines", headers=h(role)).json())


def test_default_is_simulation_and_only_admin_can_switch(client):
    assert client.get("/api/run-mode", headers=h("viewer")).json() == {"mode": "simulation"}
    for role in ("viewer", "engineer"):
        r = client.put("/api/run-mode", json={"mode": "production"}, headers=h(role))
        assert r.status_code == 403
    r = client.put("/api/run-mode", json={"mode": "production"}, headers=h("admin"))
    assert r.status_code == 200 and r.json() == {"mode": "production"}
    assert client.get("/api/run-mode", headers=h("viewer")).json() == {"mode": "production"}
    audit = client.get("/api/admin/audit", headers=h("admin")).json()
    assert any(a["action"] == "settings.run_mode" for a in audit)


def test_production_mode_shows_no_simulated_machine_anywhere(client):
    build(client)  # M100: real machine, nothing mapped yet
    put_sim_machine(client)
    assert ids(client) == ["M100", "SIM01"]  # simulation mode lists both: an unmapped machine is in both
    client.put("/api/run-mode", json={"mode": "production"}, headers=h("admin"))
    assert ids(client) == ["M100"]
    tree = client.get("/api/plant-tree", headers=h("viewer")).json()
    shown = [m["machine_id"] for w in tree["workshops"] for p in w["processes"] for m in p["machines"]]
    assert shown + [m["machine_id"] for m in tree["unplaced"]] == ["M100"]
    fleet = client.get("/api/fleet", headers=h("viewer")).json()
    assert "SIM01" not in {m["machine_id"] for m in fleet["machines"]}
    assert all(not m["is_simulated"] for m in fleet["machines"])


def test_machine_rule_follows_the_flag_and_the_mode(client):
    build(client)
    put_sim_machine(client)
    from app.api.visibility import Visibility
    from app.core.db import get_session
    from app.core.runmode import RunMode

    session = next(client.app.dependency_overrides[get_session]())
    vis = Visibility(session, client.app.state.sources, RunMode.SIMULATION)
    assert vis.machine_ok("X", False, []) is True  # nothing mapped
    assert vis.machine_ok("X", True, []) is True  # flagged simulated, simulation mode
    vis.mode = RunMode.PRODUCTION
    assert vis.machine_ok("X", True, []) is False
