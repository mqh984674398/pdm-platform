"""T005: the 20 scenarios, Golden Cases, fixtures, and reproducibility."""

import csv
import io
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.datasource.simulated import SimulatedAdapter
from app.decision.schemas import HealthState
from app.simulation.golden import DATA_DIR, load_golden_cases, load_scenarios, scenario_dir
from app.simulation.scenarios import START, scenarios, verify
from app.simulation.writer import read_text

T0 = datetime.fromisoformat(START.replace("Z", "+00:00"))
ABSTAIN_SCENARIOS = {"S13", "S14", "S15", "S16", "S17", "S18", "S20"}


def table(sid: str, name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(read_text(scenario_dir(sid) / name))))


def at_day(day: float) -> str:
    return (T0 + timedelta(days=day)).strftime("%Y-%m-%dT%H:%M")


def truth(sid: str, component: str, column: str) -> list[tuple[str, float]]:
    return [
        (r["window_start"], float(r[column]))
        for r in table(sid, "truth_components.csv")
        if r["component_id"] == component
    ]


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def test_twenty_scenarios_with_required_metadata():
    metas = load_scenarios()
    assert [m.scenario_id for m in metas] == [f"S{i:02d}" for i in range(1, 21)]
    for m in metas:
        assert m.is_simulated and m.seed and m.known_regimes
        for text in [m.title, m.expected_observable_behavior, m.ground_truth, m.expected_health_response]:
            assert text.zh and text.en
        assert m.abstention_cases, m.scenario_id
        d = scenario_dir(m.scenario_id)
        for f in [
            "raw_telemetry.csv.gz",
            "normalized.csv.gz",
            "truth_components.csv.gz",
            "topology.json",
            "config.json",
            "dataset.json",
        ]:
            assert (d / f).exists(), (m.scenario_id, f)
        assert json.loads((d / "config.json").read_text(encoding="utf-8"))["seed"] == m.seed


def test_golden_cases_reference_scenarios_and_cover_every_scenario():
    cases = load_golden_cases()
    metas = {m.scenario_id: m for m in load_scenarios()}
    assert {c.scenario_id for c in cases} == set(metas)
    for c in cases:
        assert c.case_id in metas[c.scenario_id].golden_case_ids
        topo = json.loads((scenario_dir(c.scenario_id) / "topology.json").read_text(encoding="utf-8"))
        assert c.component_id in {x["component_id"] for x in topo["components"]}
        assert set(c.signal_ids) <= {s["signal_id"] for s in topo["signals"]}


def test_abstention_expectations_present_where_required():
    cases = load_golden_cases()
    for sid in ABSTAIN_SCENARIOS:
        exps = [e for c in cases if c.scenario_id == sid for e in c.expectations]
        assert any(HealthState.UNKNOWN in e.allowed_health for e in exps), sid
    hard = {c.scenario_id for c in cases for e in c.expectations if e.must_abstain}
    assert {"S15", "S16", "S17", "S20", "S12"} <= hard


def test_no_scenario_fabricates_failure_probabilities():
    # No scenario has real failure data; RUL limitation is stated where relevant.
    texts = " ".join(a.en for m in load_scenarios() for a in m.abstention_cases)
    assert "NO_FAILURE_EVIDENCE" in texts


def test_reproducible_against_stored_checksums():
    assert verify(DATA_DIR) == []


def test_raw_and_normalized_have_same_rows():
    for s in scenarios():
        meta = json.loads((scenario_dir(s.sid) / "dataset.json").read_text(encoding="utf-8"))
        assert meta["files"]["raw_telemetry.csv.gz"]["rows"] == meta["files"]["normalized.csv.gz"]["rows"]


# --- ground truth matches each scenario's story ------------------------------------------------


def test_s03_aging_is_monotonic_and_slow():
    f = [v for _, v in truth("S03", "M01-BS1", "friction_factor")]
    assert f[-1] > f[0] and 0.1 < f[-1] - f[0] < 0.3


def test_s04_torque_drift_in_truth_and_data():
    f = truth("S04", "M01-BS1", "friction_factor")
    assert mean([v for t, v in f if t < at_day(10)]) < mean([v for t, v in f if t > at_day(25)]) - 0.5
    trq = [
        (r["ts"], abs(float(r["value"])))
        for r in table("S04", "normalized.csv")
        if r["signal_id"] == "M01-BS1.torque"
    ]
    early = [v for t, v in trq if t < at_day(10) and v > 1]
    late = [v for t, v in trq if t > at_day(25) and v > 1]
    assert mean(late) > mean(early) * 1.1


def test_s07_s08_are_direction_specific():
    for sid, changed, same in [
        ("S07", "extend_factor", "retract_factor"),
        ("S08", "retract_factor", "extend_factor"),
    ]:
        c, s = truth(sid, "M01-CY1", changed), truth(sid, "M01-CY1", same)
        assert c[-1][1] - c[0][1] > 0.35 and abs(s[-1][1] - s[0][1]) < 0.05


def test_s09_s10_lubrication_direction():
    for sid, better in [("S09", True), ("S10", False)]:
        f = truth(sid, "M01-BS1", "friction_factor")
        before = [v for t, v in f if at_day(13) < t < at_day(15)]
        after = [v for t, v in f if at_day(15.1) < t < at_day(17)]
        assert (mean(after) < mean(before)) is better, sid
        wear = [(r["window_start"], float(r["wear"])) for r in table(sid, "truth_components.csv")]
        assert wear == sorted(wear)  # aging never resets on lubrication


def test_s12_replacement_new_lifecycle_and_reset():
    rows = table("S12", "truth_components.csv")
    assert rows[0]["lifecycle_id"] == "M01-BS1-LC1" and rows[-1]["lifecycle_id"] == "M01-BS1-LC2"
    f = truth("S12", "M01-BS1", "friction_factor")
    assert (
        mean([v for t, v in f if t > at_day(22)])
        < 1.1
        < mean([v for t, v in f if at_day(18) < t < at_day(21)])
    )


def test_s17_unknown_recipe_scheduled():
    w = table("S17", "truth_windows.csv")
    assert {r["recipe_id"] for r in w if at_day(4.1) < r["window_start"] < at_day(6)} == {"R-X"}
    assert "R-X" not in load_scenarios()[16].known_regimes


def test_s19_shared_chain_affects_both_screws():
    for comp in ["M01-BS1", "M01-BS2"]:
        f = truth("S19", comp, "friction_factor")
        assert f[-1][1] - f[0][1] > 0.4


def test_s20_interruption_and_watermark_recovery():
    a = SimulatedAdapter(scenario_dir("S20"))
    gap_start = T0 + timedelta(days=3)
    before = [r for r in a.query_incremental("SIM-S20", "M01_BS1_TRQ", T0, 1_000_000) if r.ts < gap_start]
    resumed = a.query_incremental("SIM-S20", "M01_BS1_TRQ", before[-1].ts, 10)
    assert resumed[0].ts >= T0 + timedelta(days=5)


def test_s18_incomplete_operations_logged():
    log = json.loads((scenario_dir("S18") / "faults.json").read_text(encoding="utf-8"))[
        "incomplete_operations"
    ]
    assert len(log) > 10 and {e["component_id"] for e in log} == {"M01-CY1", "M01-VC1"}


@pytest.mark.parametrize(
    "name", ["S01_ball_screw_normalized.csv", "S14_linear_motor_raw.csv", "S18_cylinder_raw.csv"]
)
def test_fixtures_present(name):
    lines = (DATA_DIR / "fixtures" / name).read_text(encoding="utf-8").splitlines()
    assert len(lines) > 100


def test_scenario_start_is_utc():
    assert T0.tzinfo == UTC or T0.utcoffset() == timedelta(0)
