"""D-044: prediction configuration endpoints: roles, drafts, compile preview, immutability."""

from ..lifecycle.conftest import seed

CID = "M01-BS1"
PIPE = {"pipeline": [{"stage_id": "rules", "algorithm": "engineering-rules"}]}


def test_roles_draft_compile_and_missing_validation(client):
    seed(client, "S04")
    url = f"/api/components/{CID}/prediction-configs"
    assert client.post(url, {"content": PIPE}, role="engineer").status_code == 403
    r = client.post(url, {"content": PIPE}, role="admin")
    assert r.status_code == 200, r.text
    cfg = r.json()
    assert cfg["config_id"] == f"{CID}@v1" and cfg["status"] == "DRAFT" and cfg["content_hash"]
    assert [v["version"] for v in client.get(url).json()] == [1]  # anyone signed in can read
    comp = client.post(f"{url}/compile", PIPE, role="admin").json()
    assert comp["ok"] and comp["stages"][0]["effective"]
    # not validated: cannot publish
    pub = client.post(f"/api/prediction-configs/{cfg['config_id']}/publish", {"comment": "x"}, role="admin")
    assert pub.status_code == 409
    # the safety floor cannot be switched off through the API either
    bad = {**PIPE, "criteria": {"safety_first": False}}
    assert client.put(f"/api/prediction-configs/{cfg['config_id']}", bad, role="admin").status_code == 422
    names = [a["algorithm_id"] for a in client.get("/api/algorithm-catalog").json()]
    assert "xgboost" in names and "lstm" in names
    assert client.get("/api/prediction-configs/nope@v1").status_code == 404
