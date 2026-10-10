"""D-037/D-038: plant structure, device binding, components and shared drive chains."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.main  # noqa: F401  (registers tables)
from app.core.db import Base, get_session
from app.datasource.query_service.sources import DataSourceRegistry
from app.main import create_app


def h(role):
    return {"X-PDM-User": "u1", "X-PDM-Role": role}


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'p.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    def session():
        with factory() as s:
            yield s

    application = create_app(sources=DataSourceRegistry())
    application.dependency_overrides[get_session] = session
    return TestClient(application)


def L(zh, en):
    return {"zh": zh, "en": en}


def build(c):
    assert (
        c.put(
            "/api/plant-nodes/WS1",
            json={"node_id": "WS1", "level": "WORKSHOP", "name": L("一车间", "Workshop 1")},
            headers=h("admin"),
        ).status_code
        == 200
    )
    r = c.put(
        "/api/plant-nodes/P10",
        json={"node_id": "P10", "parent_id": "WS1", "level": "PROCESS", "name": L("装配", "Assembly")},
        headers=h("admin"),
    )
    assert r.status_code == 200
    body = {
        "machine_id": "M100",
        "name": L("装配机100", "Assembler 100"),
        "process_id": "P10",
        "device_id": "dev-100",
    }
    r = c.post("/api/plant-machines", json=body, headers=h("admin"))
    assert r.status_code == 201, r.text
    return r.json()


def test_administrator_builds_the_tree_and_paths_follow(client):
    m = build(client)
    assert m["path"] == L("一车间 / 装配", "Workshop 1 / Assembly") and m["device_id"] == "dev-100"
    tree = client.get("/api/plant-tree", headers=h("viewer")).json()
    ws = tree["workshops"][0]
    assert ws["processes"][0]["machines"][0]["machine_id"] == "M100" and tree["unplaced"] == []
    machines = client.get("/api/machines", headers=h("viewer")).json()
    assert machines[0]["path"]["en"] == "Workshop 1 / Assembly"
    # renaming the workshop updates every path
    client.put(
        "/api/plant-nodes/WS1",
        json={"node_id": "WS1", "level": "WORKSHOP", "name": L("总装车间", "Final assembly")},
        headers=h("admin"),
    )
    assert client.get("/api/machines", headers=h("viewer")).json()[0]["path"]["zh"] == "总装车间 / 装配"


def test_only_administrators_change_the_structure(client):
    build(client)
    for role in ("engineer", "maintenance", "viewer"):
        r = client.put(
            "/api/plant-nodes/WS2",
            json={"node_id": "WS2", "level": "WORKSHOP", "name": L("二", "2")},
            headers=h(role),
        )
        assert r.status_code == 403
        assert client.delete("/api/plant-machines/M100", headers=h(role)).status_code == 403


def test_rules_keep_the_tree_consistent(client):
    build(client)
    a = h("admin")
    # a process needs a workshop; a machine needs a process
    bad = client.put(
        "/api/plant-nodes/P2", json={"node_id": "P2", "level": "PROCESS", "name": L("x", "x")}, headers=a
    )
    assert bad.status_code == 409
    bad = client.post(
        "/api/plant-machines", json={"machine_id": "M2", "name": L("x", "x"), "process_id": "WS1"}, headers=a
    )
    assert bad.status_code == 409
    # one device id belongs to one machine
    dup = {"machine_id": "M2", "name": L("x", "x"), "process_id": "P10", "device_id": "dev-100"}
    assert client.post("/api/plant-machines", json=dup, headers=a).status_code == 409
    # non-empty nodes cannot be deleted
    assert client.delete("/api/plant-nodes/WS1", headers=a).status_code == 409
    assert client.delete("/api/plant-nodes/P10", headers=a).status_code == 409


def test_components_and_shared_drive_chain(client):
    build(client)
    a = h("admin")
    for cid, name in (("M100-BS1", "X"), ("M100-BS2", "Y")):
        body = {
            "component_id": cid,
            "type": "BALL_SCREW",
            "name": L(f"{name}轴丝杠", f"{name} ball screw"),
            "drive_chain_id": "M100-DC1",
        }
        r = client.put(f"/api/plant-machines/M100/components/{cid}", json=body, headers=a)
        assert r.status_code == 200, r.text
    comps = client.get("/api/machines/M100/components", headers=h("viewer")).json()
    assert [c["drive_chain_id"] for c in comps] == ["M100-DC1", "M100-DC1"]
    tree = client.get("/api/plant-tree", headers=h("viewer")).json()
    assert len(tree["workshops"][0]["processes"][0]["machines"][0]["components"]) == 2
    # type is fixed once created; machine with components cannot be deleted
    body = {"component_id": "M100-BS1", "type": "GEAR", "name": L("x", "x")}
    assert client.put("/api/plant-machines/M100/components/M100-BS1", json=body, headers=a).status_code == 409
    assert client.delete("/api/plant-machines/M100", headers=a).status_code == 409
    assert client.delete("/api/plant-components/M100-BS2", headers=a).status_code == 204
    assert (
        client.put(
            "/api/plant-machines/M100/components/M100-BS1",
            json={**body, "type": "BALL_SCREW"},
            headers=h("engineer"),
        ).status_code
        == 403
    )
