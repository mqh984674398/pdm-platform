"""T028: local sign-in, session cookie, CSRF, lockout, deactivation, production guard, static serving."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.main  # noqa: F401  (registers tables)
from app.core.audit import entries
from app.core.auth import AuthError, NewUser, UserStore, issue_token, read_token
from app.core.config import get_settings
from app.core.db import Base, get_session
from app.core.modules import MODULES
from app.core.security import Principal, Role
from app.datasource.query_service.sources import DataSourceRegistry
from app.main import create_app

from ..datasource.conftest import IOTSHARP_LIKE, source_config

SECRET = "s" * 40
ROOT = Principal(user_id="setup", role=Role.ADMIN)
PW = "correct horse battery"


@pytest.fixture
def factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'a.db'}")
    Base.metadata.create_all(engine)
    f = sessionmaker(engine, expire_on_commit=False)
    with f() as s:
        store = UserStore(s)
        store.create(NewUser(user_id="adm", display_name="Admin", role=Role.ADMIN, password=PW), ROOT)
        store.create(NewUser(user_id="tech", display_name="Tech", role=Role.MAINTENANCE, password=PW), ROOT)
    yield f
    engine.dispose()


def _app(monkeypatch, factory, **env):
    for k, v in {"PDM_AUTH_MODE": "local", "PDM_SECRET_KEY": SECRET, **env}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    application = create_app(sources=DataSourceRegistry())

    def session():
        with factory() as s:
            yield s

    application.dependency_overrides[get_session] = session
    return TestClient(application)


@pytest.fixture(autouse=True)
def _reset_settings():
    yield
    get_settings.cache_clear()


def _login(c, user="adm", pw=PW):
    return c.post("/api/auth/login", json={"user_id": user, "password": pw})


def test_token_is_signed_and_expires():
    tok = issue_token("adm", SECRET, now=1000)
    assert read_token(tok, SECRET, now=1001) == "adm"
    with pytest.raises(AuthError):
        read_token(tok.replace("adm", "root", 1), SECRET, now=1001)
    with pytest.raises(AuthError):
        read_token(tok, "x" * 40, now=1001)
    with pytest.raises(AuthError, match="expired"):
        read_token(tok, SECRET, now=1000 + 13 * 3600)


def test_local_mode_refuses_short_secret(monkeypatch):
    monkeypatch.setenv("PDM_AUTH_MODE", "local")
    monkeypatch.setenv("PDM_SECRET_KEY", "short")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="32"):
        create_app(sources=DataSourceRegistry())


def test_sign_in_sets_httponly_cookie_and_me(monkeypatch, factory):
    c = _app(monkeypatch, factory)
    assert c.get("/api/auth/me").status_code == 401
    r = _login(c)
    assert r.status_code == 200
    assert r.json() == {"user_id": "adm", "role": "admin", "mode": "local", "modules": list(MODULES)}
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert c.get("/api/auth/me").json()["role"] == "admin"
    assert c.post("/api/auth/logout", headers={"X-PDM-CSRF": "1"}).status_code == 204
    c.cookies.clear()
    assert c.get("/api/auth/me").status_code == 401


def test_dev_headers_are_ignored_in_local_mode(monkeypatch, factory):
    c = _app(monkeypatch, factory)
    r = c.get("/api/auth/users", headers={"X-PDM-User": "x", "X-PDM-Role": "admin"})
    assert r.status_code == 401


def test_state_changes_need_csrf_header(monkeypatch, factory):
    c = _app(monkeypatch, factory)
    _login(c)
    body = {"user_id": "eng1", "display_name": "E", "role": "engineer", "password": PW}
    assert c.post("/api/auth/users", json=body).status_code == 403
    r = c.post("/api/auth/users", json=body, headers={"X-PDM-CSRF": "1"})
    assert r.status_code == 200 and r.json()["role"] == "engineer"


def test_wrong_password_locks_after_five(monkeypatch, factory):
    c = _app(monkeypatch, factory)
    for _ in range(5):
        r = _login(c, "tech", "wrong password!")
        assert r.status_code == 401 and r.json()["code"] == "sign_in_failed"
    assert _login(c, "tech").status_code == 401  # locked even with the right password
    with factory() as s:
        actions = [e.action for e in entries(s)]
    assert actions.count("auth.failed") == 5 and "auth.locked" in actions


def test_unknown_user_gets_same_answer(monkeypatch, factory):
    c = _app(monkeypatch, factory)
    a, b = _login(c, "nobody", "whatever12345"), _login(c, "tech", "wrong password!")
    assert a.status_code == b.status_code == 401 and a.json()["message"] == b.json()["message"]


def test_deactivation_ends_existing_session(monkeypatch, factory):
    c = _app(monkeypatch, factory)
    tech = _app(monkeypatch, factory)
    _login(tech, "tech")
    assert tech.get("/api/auth/me").status_code == 200
    _login(c)
    r = c.put("/api/auth/users/tech", json={"active": False}, headers={"X-PDM-CSRF": "1"})
    assert r.status_code == 200
    assert tech.get("/api/auth/me").status_code == 401


def test_roles_apply_and_admin_cannot_demote_self(monkeypatch, factory):
    c = _app(monkeypatch, factory)
    _login(c, "tech")
    assert c.get("/api/auth/users").status_code == 403
    assert c.get("/api/llm/settings").status_code == 403
    _login(c)
    r = c.put("/api/auth/users/adm", json={"role": "viewer"}, headers={"X-PDM-CSRF": "1"})
    assert r.status_code == 409


def test_unknown_auth_mode_refuses(monkeypatch, factory):
    c = _app(monkeypatch, factory, PDM_AUTH_MODE="sso")
    assert c.get("/api/auth/me").status_code == 501


def test_production_sources_stay_off_until_approved(tmp_path):
    cfg = source_config(data_source_id="iot", credential_ref="secret://pdm/iot-readonly")
    f = tmp_path / "sources.json"
    item = {"config": cfg.model_dump(mode="json"), "layout": IOTSHARP_LIKE.model_dump(mode="json")}
    f.write_text(json.dumps([item]), encoding="utf-8")
    reg = DataSourceRegistry.from_file(f, allow_production=False)
    assert reg.skipped == ["iot"]
    assert get_settings().production_data_approved is False


def test_built_frontend_is_served_with_spa_fallback(monkeypatch, factory, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>pdm</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    c = _app(monkeypatch, factory, PDM_STATIC_DIR=str(dist))
    root = c.get("/")
    assert root.text == "<html>pdm</html>"
    assert root.headers["x-frame-options"] == "DENY" and root.headers["x-content-type-options"] == "nosniff"
    assert c.get("/fleet/A01").text == "<html>pdm</html>"
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert c.get("/api/nothing-here").status_code == 404
    assert c.get("/../../etc/passwd").text == "<html>pdm</html>"
