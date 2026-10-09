"""T012 AC1-AC3 on the Golden Cases of S13-S16 and S20 (SIMULATED data only)."""

from __future__ import annotations

import pytest

from app.signals.schemas import QualityFlag as Q

from .conftest import GOLDEN, all_flags, scenario

CASES = [
    pytest.param(c, e, id=f"{c['case_id']}@{e['start_h']:g}-{e['end_h']:g}h")
    for c in GOLDEN
    if c["scenario_id"] in {"S13", "S14", "S15", "S16", "S20"}
    for e in c["expectations"]
]


@pytest.mark.parametrize(("case", "exp"), CASES)
def test_golden_case_span(case, exp):
    resp = scenario(case["scenario_id"]).report(case["signal_ids"], exp["start_h"], exp["end_h"])
    flags = all_flags(resp)
    assert set(exp["required_flags"]) <= flags
    if exp["allowed_health"] == ["NORMAL"]:
        assert flags == set(), "clean spans must not raise data-quality flags"


def test_s13_missing_rows_are_counted_inside_observation_windows():
    (rep,) = scenario("S13").report(["M01-BS1.torque"], 48, 96).reports
    # 30 % of rows dropped during the fault; cadence inside each 2-minute window reveals them
    assert rep.expected_interval_s == 2.0 and rep.median_interval_s == 2.0
    assert 0.2 < rep.missing_count / (rep.sample_count + rep.missing_count) < 0.4
    assert rep.observation_window_count == 8 and rep.gap_count == 0
    assert all(Q.MISSING in s.flags for s in rep.spans)


def test_s14_jitter_out_of_order_and_sampling_interval():
    resp = scenario("S14").report(["M01-BS1.speed", "M01-LM1.speed"], 48, 120)
    bs, lm = resp.reports
    assert Q.JITTER in bs.flags and bs.interval_jitter_s > 0.1  # injected N(0, 0.3 s)
    assert abs(bs.median_interval_s - 2.0) < 0.05
    assert Q.OUT_OF_ORDER in lm.flags and lm.out_of_order_count > 0 and Q.JITTER not in lm.flags
    assert lm.duplicate_count == 0 and lm.missing_count == 0


def test_s15_misalignment_reports_tolerance_and_windows():
    resp = scenario("S15").report(["M01-BS1.speed", "M01-BS1.torque"], 48, 120)
    (a,) = resp.alignment
    assert a.tolerance_s == 1.0 and a.median_time_offset_s == 0.0  # timestamps match; values lag
    assert Q.MISALIGNED in a.flags and len(a.misaligned_windows) >= 5 and a.agreement < a.min_agreement
    fault = scenario("S15").window(48, 120)
    assert all(fault.start <= w.start and w.end <= fault.end for w in a.misaligned_windows)


def test_s14_jittered_timestamps_still_pair_within_tolerance():
    (a,) = scenario("S14").report(["M01-BS1.speed", "M01-BS1.torque"], 48, 120).alignment
    assert Q.MISALIGNED not in a.flags
    assert 0 < a.median_time_offset_s <= a.tolerance_s
    assert a.paired_count > 0.95 * (a.paired_count + a.unpaired_speed_count)


def test_s16_bias_and_unit_mismatch_are_flagged_not_corrected():
    s16 = scenario("S16")
    (a,) = s16.report(["M01-BS1.speed", "M01-BS1.torque"], 72, 120).alignment
    assert Q.BIAS_SUSPECT in a.flags
    assert a.standstill_torque - a.reference_standstill_torque == pytest.approx(0.5, abs=0.1)  # +5 %rated
    (rep,) = s16.report(["M01-VC1.release_time"], 144, 192).reports
    assert {Q.UNIT_SUSPECT, Q.OUT_OF_RANGE} <= set(rep.flags) and rep.unit_suspect
    assert rep.valid_range == (0.0, 60.0)  # unit default for seconds
    # not corrected: the delivered values stay x1000 (ms read as µs) in the source rows
    rows = s16.sources.adapter("simulated").query_range("SIM-S16", "M01_VC1_REL", s16.window(144, 192), 1000)
    assert min(r.value for r in rows) > 1000 * 50  # raw ms values scaled by 1000


def test_s20_interruption_is_one_gap_with_its_extent():
    (rep, _) = scenario("S20").report(["M01-BS1.speed", "M01-BS1.torque"], 60, 132).reports
    assert rep.gap_count == 1 and Q.GAP in rep.flags
    (gap,) = [s for s in rep.spans if Q.GAP in s.flags]
    outage = scenario("S20").window(72, 120)
    assert gap.start <= outage.start and gap.end >= outage.end
    assert rep.largest_gap_s > 48 * 3600 and rep.gap_threshold_s < 48 * 3600
