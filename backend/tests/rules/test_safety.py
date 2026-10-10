"""T017 AC2: safety rules are deterministic, versioned, and only an administrator can disable them."""

import pytest
from pydantic import ValidationError

from app.monitoring.rules.definitions import DEFAULT_RULES
from app.monitoring.rules.engine import evaluate
from app.monitoring.schemas import MonitoringLevel as L
from app.monitoring.schemas import RuleKind

from ..features.conftest import extraction
from .conftest import after_reference, scenario


def test_rule_set_is_versioned_and_immutable():
    assert DEFAULT_RULES.ref == "pdm-rules@1.0.0"
    safety = [r for r in DEFAULT_RULES.rules if r.kind == RuleKind.SAFETY]
    assert {r.rule_id for r in safety} == {"SF-INCOMPLETE", "SF-TORQUE-LIMIT"}
    with pytest.raises(ValidationError):
        safety[0].warning = 0.99  # thresholds change only with a new rule set version


def test_incomplete_operations_rule_needs_no_reference():
    # S18: actuator timeouts 72–168 h; the golden case allows WATCH there and NORMAL after 180 h
    sc = scenario("S18")
    vs = [v for v in extraction("S18").vectors if v.component_id == "M01-CY1"]
    evals = evaluate(vs, {}, DEFAULT_RULES)
    during = [e for e in evals if 72 <= sc.hours_of(e.window.start) < 168]
    after = [e for e in evals if sc.hours_of(e.window.start) >= 180]
    assert any(h.rule_id == "SF-INCOMPLETE" for e in during for h in e.hits)
    assert all(e.level in (L.NORMAL, L.WATCH) for e in during)
    assert after and all(e.level == L.NORMAL for e in after)


def test_torque_limit():
    vs = after_reference("S04", "M01-BS1")
    p95 = max(v.values["torque_p95"] for v in vs)
    evals = evaluate(vs, {}, DEFAULT_RULES, limits={"M01-BS1": p95 * 0.95})
    hits = [h for e in evals for h in e.hits if h.rule_id == "SF-TORQUE-LIMIT"]
    assert hits and L.CRITICAL in {h.level for h in hits}
    assert all(h.kind == RuleKind.SAFETY for h in hits)


def test_disabled_rules_are_not_evaluated():
    vs = after_reference("S04", "M01-BS1")
    evals = evaluate(vs, {}, DEFAULT_RULES, disabled={"SF-TORQUE-LIMIT"}, limits={"M01-BS1": 0.1})
    assert all(not e.hits for e in evals)


def test_only_admin_changes_safety_rules(client):
    off = {"enabled": False, "comment": "sensor replaced, limit under review"}
    before = client.get("/api/rules").json()
    assert before["config_version"] == "pdm-rules@1.0.0+0"
    assert all(s["enabled"] for s in before["states"])
    assert client.put("/api/rules/SF-TORQUE-LIMIT", off, role="engineer").status_code == 403
    assert client.put("/api/rules/SF-TORQUE-LIMIT", off, role="maintenance").status_code == 403
    assert (
        client.put("/api/rules/SF-TORQUE-LIMIT", {"enabled": False, "comment": ""}, role="admin").status_code
        == 422
    )
    r = client.put("/api/rules/SF-TORQUE-LIMIT", off, role="admin")
    assert r.status_code == 200, r.text
    state = next(s for s in r.json()["states"] if s["rule_id"] == "SF-TORQUE-LIMIT")
    assert state["enabled"] is False and state["changed_by"] == "u1"
    assert r.json()["config_version"] == "pdm-rules@1.0.0+1"
    # statistical rules: engineer
    assert client.put("/api/rules/ST-RIPPLE", off, role="maintenance").status_code == 403
    assert client.put("/api/rules/ST-RIPPLE", off, role="engineer").status_code == 200
    assert client.put("/api/rules/NOPE", off, role="admin").status_code == 404
    audit = client.get("/api/admin/audit", role="admin").json()
    rows = audit["items"] if isinstance(audit, dict) else audit
    assert [(a["action"], a["object_id"]) for a in rows if a["action"].startswith("rule.")] == [
        ("rule.disable", "SF-TORQUE-LIMIT"),
        ("rule.disable", "ST-RIPPLE"),
    ]
