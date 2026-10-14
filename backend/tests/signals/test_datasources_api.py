"""D-044: administrators manage TDengine sources in the application. The TDengine server is faked."""

import httpx
import pytest

import app.api.datasources as api
import app.datasource.managed as managed

from ..query_service.test_tdengine import FakeTaos


class ReadOnlyTaos(FakeTaos):
    def __call__(self, request):
        low = request.content.decode().lower()
        if "current_user" in low:
            self.statements.append(low)
            return self.ok([("current_user()", "VARCHAR")], [["reader@%"]])
        if low.startswith("show users"):
            return self.ok([("name", "VARCHAR"), ("super", "TINYINT")], [["reader", 0]])
        if low.startswith("show user privileges"):
            return self.ok([("user_name", "VARCHAR"), ("privilege", "VARCHAR")], [["reader", "read"]])
        return super().__call__(request)


@pytest.fixture(autouse=True)
def fake(monkeypatch, tmp_path):
    monkeypatch.setattr(managed, "TRANSPORT", httpx.MockTransport(ReadOnlyTaos()))
    monkeypatch.setattr(api, "ENV_PATH", tmp_path / ".env")
    monkeypatch.delenv("PDM_SECRET_TAOS_PLANT", raising=False)
    yield
    monkeypatch.delenv("PDM_SECRET_TAOS_PLANT", raising=False)


BODY = {
    "data_source_id": "taos-plant", "name": "涛思生产库", "host": "10.0.0.5", "port": 6041,
    "database": "plant", "stable": "meters", "device_tag": "device_id",
    "user": "reader", "password": "s3cret",
}  # fmt: skip


def test_admin_creates_tests_and_deletes_a_source(client, tmp_path):
    assert client.put("/api/admin/datasources/taos-plant", BODY, role="engineer").status_code == 403
    r = client.put("/api/admin/datasources/taos-plant", BODY)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["managed"] and out["active"] and out["credential_set"] and not out["layout"]["verified"]
    assert "s3cret" not in r.text and "reader" not in r.text  # the account is never returned
    assert "PDM_SECRET_TAOS_PLANT=reader:s3cret" in (tmp_path / ".env").read_text()
    # visible to the Studio like any production source
    ids = [s["data_source_id"] for s in client.get("/api/datasources", role="engineer").json()]
    assert "taos-plant" in ids
    checks = {
        c["key"]: c["ok"]
        for c in client.post("/api/admin/datasources/taos-plant/test", {}, role="admin").json()
    }
    assert checks == {"credential": True, "reachable": True, "readOnly": True, "layout": True,
                      "timeout": True, "rowLimit": True}  # fmt: skip
    listed = next(
        s
        for s in client.get("/api/admin/datasources", role="admin").json()
        if s["data_source_id"] == "taos-plant"
    )
    assert listed["layout"]["verified"]  # set only by a successful test against the database
    assert client.delete("/api/admin/datasources/taos-plant").status_code == 204
    assert "PDM_SECRET_TAOS_PLANT" not in (tmp_path / ".env").read_text()
    assert "taos-plant" not in [
        s["data_source_id"] for s in client.get("/api/admin/datasources", role="admin").json()
    ]


def test_file_sources_cannot_be_edited_and_ids_are_checked(client):
    assert (
        client.put("/api/admin/datasources/sim-iot", {**BODY, "data_source_id": "sim-iot"}).status_code == 409
    )
    assert client.put("/api/admin/datasources/x", BODY).status_code == 409  # id mismatch
    assert client.put("/api/admin/datasources/taos-plant", {**BODY, "password": None}).status_code == 409
    assert client.put("/api/admin/datasources/taos-plant", {**BODY, "host": "a b"}).status_code == 422


def test_source_without_account_is_inactive_and_test_says_so(client):
    body = {k: v for k, v in BODY.items() if k not in ("user", "password")}
    out = client.put("/api/admin/datasources/taos-plant", body).json()
    assert not out["active"] and not out["credential_set"]
    assert client.post("/api/admin/datasources/taos-plant/test", {}, role="admin").json() == [
        {"key": "credential", "ok": False}
    ]
