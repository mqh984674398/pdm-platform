from fastapi.testclient import TestClient

from app import __version__
from app.main import create_app


def test_health_ok_without_llm():
    resp = TestClient(create_app()).get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok", "version": __version__, "llm_enabled": False, "llm_required": False}
