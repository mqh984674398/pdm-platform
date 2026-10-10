"""D-033: account deletion and renaming, last-administrator guard, per-role module visibility."""

from __future__ import annotations

import pytest

from app.core.audit import entries
from app.core.modules import MODULES, ModuleError, ModuleStore
from app.core.security import Principal, Role

from .test_auth import PW, _app, _login, _reset_settings, factory  # noqa: F401  (fixtures)

CSRF = {"X-PDM-CSRF": "1"}


def _new(c, user_id, role):
    body = {"user_id": user_id, "display_name": user_id.title(), "role": role, "password": PW}
    assert c.post("/api/auth/users", json=body, headers=CSRF).status_code == 200


def test_admin_registers_renames_and_deletes(monkeypatch, factory):  # noqa: F811
    c = _app(monkeypatch, factory)
    _login(c)
    _new(c, "eng1", "engineer")
    r = c.put("/api/auth/users/eng1", json={"display_name": "Engineer One"}, headers=CSRF)
    assert r.status_code == 200 and r.json()["display_name"] == "Engineer One"
    assert c.delete("/api/auth/users/eng1", headers=CSRF).status_code == 204
    assert "eng1" not in {u["user_id"] for u in c.get("/api/auth/users").json()}
    assert c.delete("/api/auth/users/eng1", headers=CSRF).status_code == 409
    with factory() as s:
        assert "user.delete" in [e.action for e in entries(s, "user", "eng1")]
    _new(c, "eng1", "engineer")  # the name can be registered again


def test_cannot_delete_self_or_the_last_admin(monkeypatch, factory):  # noqa: F811
    c = _app(monkeypatch, factory)
    _login(c)
    assert c.delete("/api/auth/users/adm", headers=CSRF).status_code == 409
    _new(c, "adm2", "admin")
    other = _app(monkeypatch, factory)
    _login(other, "adm2")
    # adm2 deactivates adm, then adm2 is the last active admin and cannot be removed by anyone
    assert other.put("/api/auth/users/adm", json={"active": False}, headers=CSRF).status_code == 200
    with factory() as s:
        from app.core.auth import AccountError, UserStore

        with pytest.raises(AccountError, match="last active administrator"):
            UserStore(s).delete("adm2", Principal(user_id="setup", role=Role.ADMIN))


def test_non_admins_cannot_manage_accounts_or_modules(monkeypatch, factory):  # noqa: F811
    c = _app(monkeypatch, factory)
    _login(c, "tech")
    assert c.delete("/api/auth/users/adm", headers=CSRF).status_code == 403
    assert c.get("/api/auth/role-modules").status_code == 403
    assert c.put("/api/auth/role-modules/viewer", json={"modules": []}, headers=CSRF).status_code == 403


def test_role_modules_default_to_everything_and_admin_is_fixed(monkeypatch, factory):  # noqa: F811
    c = _app(monkeypatch, factory)
    _login(c)
    rows = {r["role"]: r for r in c.get("/api/auth/role-modules").json()}
    assert all(r["modules"] == list(MODULES) for r in rows.values())
    assert rows["admin"]["editable"] is False and rows["viewer"]["editable"] is True
    r = c.put("/api/auth/role-modules/admin", json={"modules": ["overview"]}, headers=CSRF)
    assert r.status_code == 422
    r = c.put("/api/auth/role-modules/viewer", json={"modules": ["nope"]}, headers=CSRF)
    assert r.status_code == 422


def test_module_setting_hides_and_refuses(monkeypatch, factory):  # noqa: F811
    admin = _app(monkeypatch, factory)
    _login(admin)
    r = admin.put(
        "/api/auth/role-modules/maintenance",
        json={"modules": ["alarms", "overview", "maintenance"]},
        headers=CSRF,
    )
    assert r.status_code == 200 and r.json()["modules"] == ["overview", "maintenance", "alarms"]
    tech = _app(monkeypatch, factory)
    _login(tech, "tech")
    assert tech.get("/api/auth/me").json()["modules"] == ["overview", "maintenance", "alarms"]
    # module-owned endpoints are refused; shared monitoring reads stay available
    assert tech.get("/api/query-templates").status_code == 403
    assert tech.get("/api/llm/documents").status_code == 403
    assert tech.get("/api/alarms").status_code == 200
    assert tech.get("/api/signal-config").status_code == 200
    # feedback belongs to alarms or the assistant; the role has alarms
    assert tech.get("/api/feedback").status_code != 403
    with factory() as s:
        e = [x for x in entries(s, "role", "maintenance") if x.action == "role.modules"][-1]
        assert "datasource" in e.details["removed"]


def test_store_orders_modules_and_keeps_admin_unrestricted(factory):  # noqa: F811
    with factory() as s:
        store = ModuleStore(s)
        root = Principal(user_id="setup", role=Role.ADMIN)
        assert store.set(Role.VIEWER, ["models", "overview"], root).modules == ["overview", "models"]
        assert store.visible(Role.VIEWER) == ["overview", "models"]
        assert store.visible(Role.ADMIN) == list(MODULES)
        with pytest.raises(ModuleError):
            store.set(Role.VIEWER, [], Principal(user_id="e", role=Role.ENGINEER))
