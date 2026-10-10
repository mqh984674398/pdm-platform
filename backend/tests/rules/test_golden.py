"""T017 AC1: rule levels match the Golden Cases of S04–S08 and S19; S01 raises nothing (SIMULATED).

The rules are evaluated from the end of the verified reference period (168 h). Before that no level
is produced, which the NORMAL expectations of those spans allow."""

import pytest

from app.monitoring.alarms.service import AlarmService
from app.monitoring.rules.definitions import DEFAULT_RULES
from app.monitoring.rules.engine import evaluate

from ..baselines.conftest import ENGINEER
from .conftest import GOLDEN, after_reference, references, scenario

SCENARIOS = ["S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S19"]
CASES = [pytest.param(c, id=c["case_id"]) for c in GOLDEN if c["scenario_id"] in SCENARIOS]


@pytest.mark.parametrize("case", CASES)
def test_golden_case(case, db):
    sid, cid = case["scenario_id"], case["component_id"]
    sc = scenario(sid)
    ref = references(db, sid)[cid]
    evals = evaluate(after_reference(sid, cid), {ref.lifecycle_id: ref}, DEFAULT_RULES)
    assert evals and all(e.is_simulated for e in evals)
    for exp in case["expectations"]:
        span = [e for e in evals if exp["start_h"] <= sc.hours_of(e.window.start) < exp["end_h"]]
        if exp["end_h"] > 192:
            assert span, f"no evaluated windows in {exp['start_h']}-{exp['end_h']} h"
        wrong = [
            (round(sc.hours_of(e.window.start)), e.level.value)
            for e in span
            if e.level.value not in exp["allowed_health"]
        ]
        assert wrong == [], f"{exp['start_h']}-{exp['end_h']} h allows {exp['allowed_health']}"


def test_healthy_scenario_raises_no_alarm(db):
    refs = references(db, "S01")
    evals = []
    for cid, ref in refs.items():
        evals += evaluate(after_reference("S01", cid), {ref.lifecycle_id: ref}, DEFAULT_RULES)
    raised, _ = AlarmService(db).sync(evals, ENGINEER)
    assert len(evals) > 80 and raised == []


EXPECTED_RULE = [
    ("S04", "M01-BS1", "ST-TORQUE"),
    ("S05", "M01-LM1", "ST-RIPPLE"),
    ("S06", "M01-VC1", "ST-RELEASE"),
    ("S07", "M01-CY1", "ST-EXTEND"),
    ("S08", "M01-CY1", "ST-RETRACT"),
    ("S19", "M01-BS1", "ST-TORQUE"),
    ("S19", "M01-BS2", "ST-TORQUE"),
]


@pytest.mark.parametrize(("sid", "cid", "rule"), EXPECTED_RULE)
def test_fault_reaches_the_expected_rule(sid, cid, rule, db):
    ref = references(db, sid)[cid]
    evals = evaluate(after_reference(sid, cid), {ref.lifecycle_id: ref}, DEFAULT_RULES)
    levels: dict[str, set[str]] = {}
    for h in (h for e in evals for h in e.hits):
        levels.setdefault(h.rule_id, set()).add(h.level.value)
    assert "CRITICAL" in levels[rule] or "WARNING" in levels[rule]
    # other rules on the same component stay at WATCH at most (e.g. the other cylinder direction ages)
    assert all(lv <= {"WATCH"} for rid, lv in levels.items() if rid != rule), levels
