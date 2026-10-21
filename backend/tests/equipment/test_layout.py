"""D-054: order and background picture of machines on the equipment overview."""

from __future__ import annotations

from .test_plant import L, build, h
from .test_run_mode import client  # noqa: F401  (fixture)

PNG = "data:image/png;base64,iVBORw0KGgo="


def second_machine(c):
    body = {
        "machine_id": "M200",
        "name": L("装配机200", "Assembler 200"),
        "process_id": "P10",
        "device_id": "dev-200",
    }
    assert c.post("/api/plant-machines", json=body, headers=h("admin")).status_code == 201


def test_order_and_background_are_saved_and_read_by_everyone(client):  # noqa: F811
    build(client)
    second_machine(client)
    r = client.put("/api/machine-layout/order", json={"machine_ids": ["M200", "M100"]}, headers=h("admin"))
    assert r.status_code == 204
    r = client.put("/api/machine-layout/M100/background", json={"image": PNG}, headers=h("admin"))
    assert r.status_code == 204
    layout = {m["machine_id"]: m for m in client.get("/api/machine-layout", headers=h("viewer")).json()}
    assert layout["M200"]["sort"] == 0 and layout["M100"]["sort"] == 1
    assert layout["M100"]["background"] == PNG and layout["M200"]["background"] is None
    client.put("/api/machine-layout/M100/background", json={"image": None}, headers=h("admin"))
    assert client.get("/api/machine-layout", headers=h("viewer")).json()[0]["background"] is None


def test_only_administrators_change_the_layout_and_pictures_are_checked(client):  # noqa: F811
    build(client)
    for role in ("viewer", "engineer"):
        assert (
            client.put(
                "/api/machine-layout/order", json={"machine_ids": ["M100"]}, headers=h(role)
            ).status_code
            == 403
        )
        assert (
            client.put(
                "/api/machine-layout/M100/background", json={"image": PNG}, headers=h(role)
            ).status_code
            == 403
        )
    bad = client.put(
        "/api/machine-layout/M100/background",
        json={"image": "data:text/html;base64,AAAA"},
        headers=h("admin"),
    )
    assert bad.status_code == 422
    assert (
        client.put("/api/machine-layout/NOPE/background", json={"image": PNG}, headers=h("admin")).status_code
        == 404
    )


def test_deleting_a_machine_removes_its_layout(client):  # noqa: F811
    build(client)
    client.put("/api/machine-layout/M100/background", json={"image": PNG}, headers=h("admin"))
    assert client.delete("/api/plant-machines/M100", headers=h("admin")).status_code == 204
    assert client.get("/api/machine-layout", headers=h("viewer")).json() == []
