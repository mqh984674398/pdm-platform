"""T011 AC1: CRUD for signal definitions, mappings, groups, and charts; every change is a version."""

from __future__ import annotations

from .conftest import chart, group, mapping, signal

ENG = "engineer"


def put(client, path, item, role=ENG, **meta):
    return client.put(f"/api/signal-config/{path}", {"item": item, **meta}, role=role)


def seed(client):
    """signal -> mapping -> group -> chart: versions 1..4."""
    assert put(client, "signals/M01-BS1.speed", signal()).json()["version"] == 1
    assert put(client, "mappings/M01-BS1.speed", mapping()).json()["version"] == 2
    assert put(client, "groups/SIM-S13.G1", group()).json()["version"] == 3
    assert put(client, "visualizations/viz-SIM-S13.G1", chart()).json()["version"] == 4


def test_every_change_creates_a_version(client):
    assert client.get("/api/signal-config").json() == {
        "version": None,
        "content": {"signals": [], "mappings": [], "groups": [], "visualizations": []},
    }
    seed(client)
    state = client.get("/api/signal-config").json()
    assert state["version"]["version"] == 4
    assert [len(state["content"][k]) for k in ("signals", "mappings", "groups", "visualizations")] == [
        1,
        1,
        1,
        1,
    ]
    # update in place
    resp = put(client, "signals/M01-BS1.speed", signal(valid_max=6000.0), comment="limit")
    assert resp.status_code == 200 and resp.json()["version"] == 5 and resp.json()["comment"] == "limit"
    # delete in dependency order
    for path in (
        "visualizations/viz-SIM-S13.G1",
        "groups/SIM-S13.G1",
        "mappings/M01-BS1.speed",
        "signals/M01-BS1.speed",
    ):
        assert client.delete(f"/api/signal-config/{path}?comment=cleanup", role=ENG).status_code == 200
    versions = client.get("/api/signal-config/versions").json()
    assert [v["version"] for v in versions] == list(range(9, 0, -1))
    assert all(v["content_hash"].startswith("sha256:") and v["created_by"] == "u1" for v in versions)


def test_old_versions_stay_readable_and_unchanged(client):
    seed(client)
    put(client, "signals/M01-BS1.speed", signal(valid_max=6000.0))
    v4 = client.get("/api/signal-config/versions/4").json()
    v5 = client.get("/api/signal-config/versions/5").json()
    assert v4["content"]["signals"][0]["valid_max"] is None
    assert v5["content"]["signals"][0]["valid_max"] == 6000.0
    assert v4["content_hash"] != v5["content_hash"]
    assert client.get("/api/signal-config/versions/99").status_code == 404


def test_invariants_are_enforced_and_nothing_is_saved(client):
    seed(client)
    cases = [
        (client.delete("/api/signal-config/signals/M01-BS1.speed", role=ENG), "undefined signal"),
        (
            put(client, "mappings/M01-BS1.torque", mapping("M01-BS1.torque", "M01_BS1_TRQ")),
            "undefined signal",
        ),
        (put(client, "mappings/M01-BS1.speed", mapping(unit="N*m")), "signal's unit is 'rpm'"),
        (put(client, "groups/G2", group("G2", ["nope"])), "undefined signal 'nope'"),
        (put(client, "signals/M01-BS1.speed", signal()), "no changes"),
        (put(client, "signals/other", signal()), "must match the URL"),
    ]
    for resp, reason in cases:
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "config_conflict"
        assert reason in resp.json()["detail"]["reason"]
    assert client.get("/api/signal-config").json()["version"]["version"] == 4


def test_two_signals_cannot_share_a_device_key(client):
    seed(client)
    put(client, "signals/dup", signal("dup"))
    resp = put(client, "mappings/dup", mapping("dup"))
    assert resp.status_code == 409 and "duplicate device key" in resp.json()["detail"]["reason"]


def test_stale_base_version_is_rejected(client):
    assert put(client, "signals/a", signal("a"), base_version=0).status_code == 200
    resp = put(client, "signals/b", signal("b"), base_version=0)
    assert resp.status_code == 409 and "changed since version 0" in resp.json()["detail"]["reason"]
    assert put(client, "signals/b", signal("b"), base_version=1).json()["version"] == 2


def test_unknown_item_delete_is_404(client):
    assert client.delete("/api/signal-config/groups/none", role=ENG).status_code == 404


def test_roles(client):
    assert client.get("/api/signal-config", role="viewer").status_code == 200
    assert put(client, "signals/a", signal("a"), role="viewer").status_code == 403
    assert put(client, "signals/a", signal("a"), role="maintenance").status_code == 403
    assert client.delete("/api/signal-config/signals/a", role="viewer").status_code == 403
    assert client.http.get("/api/signal-config").status_code == 401


def test_changes_are_audited(client):
    seed(client)
    client.delete("/api/signal-config/visualizations/viz-SIM-S13.G1?comment=drop", role=ENG)
    log = client.get("/api/admin/audit?object_type=signal_config", role="admin").json()
    assert [e["action"] for e in log] == ["signal_config.create"] * 4 + ["signal_config.delete"]
    last = log[-1]
    assert last["actor"] == "u1" and last["actor_role"] == "engineer" and last["object_id"] == "5"
    assert last["details"]["collection"] == "visualizations" and last["details"]["previous_version"] == 4
    assert last["details"]["comment"] == "drop" and last["details"]["content_hash"].startswith("sha256:")


def device_change(device="SIM-S13", comment="studio save", **kw):
    sid = f"{device}.speed"
    body = {
        "signals": [signal(sid)],
        "mappings": [mapping(sid, device=device)],
        "groups": [group(f"{device}.G1", [sid])],
        "visualizations": [chart(f"viz-{device}.G1", [sid])],
        "comment": comment,
    }
    body.update(kw)
    return body


def test_device_save_replaces_only_that_device(client):
    url = "/api/signal-config/sources/sim-iot/devices/{}"
    assert client.put(url.format("SIM-S13"), device_change("SIM-S13"), role=ENG).json()["version"] == 1
    assert client.put(url.format("SIM-S14"), device_change("SIM-S14"), role=ENG).json()["version"] == 2
    # re-save S13 with a different signal id: the old S13 signal, group, and chart go away
    body = device_change("SIM-S13", comment="rename")
    body["signals"][0]["signal_id"] = body["mappings"][0]["signal_id"] = "SIM-S13.spd"
    body["groups"][0]["signal_ids"] = body["visualizations"][0]["signal_ids"] = ["SIM-S13.spd"]
    assert client.put(url.format("SIM-S13"), body, role=ENG).json()["version"] == 3
    content = client.get("/api/signal-config").json()["content"]
    assert sorted(s["signal_id"] for s in content["signals"]) == ["SIM-S13.spd", "SIM-S14.speed"]
    assert sorted(g["group_id"] for g in content["groups"]) == ["SIM-S13.G1", "SIM-S14.G1"]
    assert len(content["visualizations"]) == 2


def test_device_save_rejects_other_devices_and_collisions(client):
    url = "/api/signal-config/sources/sim-iot/devices/SIM-S13"
    resp = client.put(url, device_change("SIM-S14"), role=ENG)
    assert resp.status_code == 409 and "other devices" in resp.json()["detail"]["reason"]
    client.put("/api/signal-config/sources/sim-iot/devices/SIM-S14", device_change("SIM-S14"), role=ENG)
    clash = device_change("SIM-S13")
    clash["signals"][0]["signal_id"] = clash["mappings"][0]["signal_id"] = "SIM-S14.speed"
    clash["groups"] = clash["visualizations"] = []
    resp = client.put(url, clash, role=ENG)
    assert resp.status_code == 409 and "duplicate signal 'SIM-S14.speed'" in resp.json()["detail"]["reason"]
    assert (
        client.put("/api/signal-config/sources/nope/devices/X", device_change(), role=ENG).status_code == 404
    )
