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
    # the passing test also registers the standard read-only templates, so mapping can use the source
    tpl = client.get("/api/query-templates", role="engineer").json()
    assert any(t["data_source_id"] == "taos-plant" for t in tpl)
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
    checks = client.post("/api/admin/datasources/taos-plant/test", {}, role="admin").json()
    assert [(c["key"], c["ok"]) for c in checks] == [("credential", False)]


def test_pasted_address_is_split_into_host_scheme_and_port(client):
    body = {**BODY, "host": "https://10.0.0.5:6041/rest/sql", "port": 6041, "scheme": "http"}
    out = client.put("/api/admin/datasources/taos-plant", body).json()
    assert (out["host"], out["port"], out["scheme"]) == ("10.0.0.5", 6041, "https")
    out = client.put("/api/admin/datasources/taos-plant", {**BODY, "host": "10.0.0.5:6060"}).json()
    assert (out["host"], out["port"]) == ("10.0.0.5", 6060)


def test_failed_test_says_why_and_wrong_port_is_called_out(client):
    client.put("/api/admin/datasources/taos-plant", {**BODY, "port": 6060})

    def page(request):  # taosExplorer answers with a web page, not taosAdapter's JSON
        return httpx.Response(404, text="<html>not found</html>")

    managed.TRANSPORT = httpx.MockTransport(page)
    try:
        # the stored source keeps the transport it was built with; rebuild it through a new save
        client.put("/api/admin/datasources/taos-plant", {**BODY, "port": 6060})
        checks = client.post("/api/admin/datasources/taos-plant/test", {}, role="admin").json()
    finally:
        managed.TRANSPORT = httpx.MockTransport(ReadOnlyTaos())
    reach = next(c for c in checks if c["key"] == "reachable")
    assert not reach["ok"] and reach["hint"] == "port_explorer" and "HTTP 404" in reach["detail"]


def test_wrong_tag_column_lists_what_the_table_has_and_structure_can_be_read(client):
    client.put("/api/admin/datasources/taos-plant", {**BODY, "stable": "meters", "device_tag": "APAC000Y"})
    checks = client.post("/api/admin/datasources/taos-plant/test", {}, role="admin").json()
    layout = next(c for c in checks if c["key"] == "layout")
    assert not layout["ok"] and layout["hint"] == "layout"
    assert "APAC000Y" in layout["detail"] and "device_id (tag)" in layout["detail"]
    r = client.get("/api/admin/datasources/taos-plant/structure", role="admin")
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["stables"] == ["meters"] and st["stable"] == "meters"
    assert {c["name"]: c["is_tag"] for c in st["columns"]} == {
        "ts": False, "torque": False, "speed": False, "device_id": True,
    }  # fmt: skip
    assert client.get("/api/admin/datasources/taos-plant/structure", role="engineer").status_code == 403
