"""T024: evidence fusion, aging grading (D-022), safety precedence and recommendations."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.schemas import LocalizedText, ResultMeta, TimeWindow
from app.decision.aging import assess
from app.decision.fusion import (
    INTERPRETATION,
    FusionInput,
    Preconditions,
    ProposalSource,
    fuse,
    guard,
    interpret,
)
from app.decision.schemas import HealthState, RecommendationPriority
from app.equipment.schemas import ComponentType
from app.monitoring.schemas import MonitoringLevel, RuleHit, RuleKind, WindowEvaluation
from app.prediction.schemas import (
    AnomalyScoreResult,
    ClassProbabilityResult,
    DegradationIndicatorResult,
    FailureProbabilityResult,
    OutputKind,
    UnsupportedPrediction,
    UnsupportedReason,
)

from .conftest import graded

T0 = datetime(2026, 1, 1, tzinfo=UTC)
BS = ComponentType.BALL_SCREW
H = HealthState


def window(h: float, persistent: float = 0.0, hits=(), evaluated=True) -> WindowEvaluation:
    w = TimeWindow(start=T0 + timedelta(hours=h), end=T0 + timedelta(hours=h + 1))
    lvl = max((x.level for x in hits), key=list(MonitoringLevel).index, default=MonitoringLevel.NORMAL)
    return WindowEvaluation(
        component_id="C1",
        lifecycle_id="C1-LC1",
        window=w,
        feature_ref="ball_screw@1.1.0",
        level=lvl,
        evaluated=evaluated,
        hits=list(hits),
        statistics={"ST-TORQUE:persistent": persistent},
        not_evaluated=[],
        rules_version="pdm-rules@1.0.0",
        is_simulated=True,
    )


def stat(level: str, value: float = 5.0) -> RuleHit:
    return RuleHit(
        rule_id="ST-TORQUE",
        kind=RuleKind.STATISTICAL,
        level=MonitoringLevel(level),
        feature="torque_cruise_mean",
        value=value,
        threshold=4.0,
    )


def safety(level: str = "CRITICAL") -> RuleHit:
    return RuleHit(
        rule_id="SAFE-TORQUE",
        kind=RuleKind.SAFETY,
        level=MonitoringLevel(level),
        feature="torque_peak",
        value=99.0,
        threshold=90.0,
        basis="raw",
    )


def series(rate: float, days: int, jump_at: int | None = None, hits=()) -> list[WindowEvaluation]:
    out = []
    for i in range(days * 2):
        h = i * 12.0
        v = (
            rate * h / 24
            + (6.0 if jump_at is not None and h / 24 >= jump_at else 0.0)
            + (0.3 if i % 2 else -0.3)
        )
        out.append(window(h, v))
    last = out[-1]
    out[-1] = last.model_copy(update={"hits": list(hits), "level": hits[0].level if hits else last.level})
    return out


def inp(hist, predictions=(), pre=None) -> FusionInput:
    return FusionInput(
        "C1", BS, "C1-LC1", T0, hist[-1] if hist else None, hist, list(predictions), pre or Preconditions()
    )


def meta() -> ResultMeta:
    return ResultMeta(
        model_version="m@1.0.0",
        feature_version="ball_screw@1.1.0",
        config_version="REF-1",
        computed_at=T0,
        data_window=TimeWindow(start=T0, end=T0 + timedelta(hours=1)),
        is_simulated=True,
    )


def base(**kw):
    return {
        "operator_id": "op@1.0.0",
        "component_id": "C1",
        "lifecycle_id": "C1-LC1",
        "regime_id": None,
        "meta": meta(),
        **kw,
    }


DEG_HIGH = DegradationIndicatorResult(
    **base(value=8.0, unit="z", reference_baseline_id="R", higher_is_worse=True)
)
DEG_LOW = DegradationIndicatorResult(
    **base(value=0.2, unit="z", reference_baseline_id="R", higher_is_worse=True)
)
ANOM_HIGH = AnomalyScoreResult(**base(score=9.0, threshold=4.0, scale="z"))
CLS_HEALTHY = ClassProbabilityResult(
    **base(probabilities={"healthy": 0.95, "degraded": 0.05}, calibrated=False)
)
FAIL = FailureProbabilityResult(
    **base(probability=0.9, horizon_hours=24, failure_events_in_training=3, censoring_method="km")
)
UNSUP = UnsupportedPrediction(
    **base(
        requested_kind=OutputKind.ANOMALY_SCORE,
        reason=UnsupportedReason.INELIGIBLE_INPUT,
        detail=LocalizedText(zh="x", en="regime not supported"),
    )
)


# --- AC1: typed outputs only through explicit interpretation --------------------------------------


def test_every_result_kind_has_an_explicit_interpretation_rule():
    kinds = {"unsupported"} | {k.value for k in OutputKind}
    assert set(INTERPRETATION) == kinds
    assert interpret(FAIL) is None and interpret(UNSUP) is None
    assert interpret(AnomalyScoreResult(**base(score=9.0, threshold=None, scale="?"))).value == "NEUTRAL"


def test_failure_probability_and_unsupported_never_set_the_level():
    r = fuse(inp([window(0)], [FAIL, UNSUP]))
    assert r.decision.health_state == H.NORMAL
    ev = {e.result_ref: e for e in r.evidence if e.source == "MODEL"}
    assert len(ev) == 1 and not next(iter(ev.values())).eligible


# --- AC2: conflicts and low eligibility -----------------------------------------------------------


def test_models_alone_raise_at_most_watch_and_flag_conflict():
    r = fuse(inp([window(0)], [DEG_HIGH, ANOM_HIGH]))
    assert r.decision.health_state == H.WATCH and r.decision.conflicting_evidence
    assert any("WATCH" in x.en for x in r.decision.reasons)


def test_rules_high_but_models_healthy_is_watch_with_reason():
    r = fuse(inp([window(0, 12, [stat("WARNING", 12)])], [CLS_HEALTHY]))
    assert r.decision.health_state == H.WATCH and r.decision.conflicting_evidence
    assert any("conflicting" in x.en for x in r.decision.reasons)


def test_models_disagreeing_with_each_other_is_watch():
    r = fuse(inp([window(0)], [DEG_HIGH, DEG_LOW]))
    assert r.decision.health_state == H.WATCH and r.decision.conflicting_evidence


@pytest.mark.parametrize(
    ("hist", "pre", "word"),
    [
        ([], Preconditions(), "evaluable"),
        ([window(0, evaluated=False)], Preconditions(), "evaluable"),
        ([window(0)], Preconditions(reference_verified=False), "reference"),
        ([window(0)], Preconditions(validation_running=True), "validation"),
        ([window(0)], Preconditions(stale_hours=30), "30 h"),
    ],
)
def test_low_eligibility_abstains_with_reason_even_if_models_are_sure(hist, pre, word):
    r = fuse(inp(hist, [DEG_HIGH, ANOM_HIGH], pre))
    assert r.decision.health_state == H.UNKNOWN
    assert word in r.decision.reasons[0].en
    (rec,) = r.recommendations
    assert rec.priority == RecommendationPriority.INFO and rec.evidence_ids


def test_ineligible_model_outputs_are_reported():
    r = fuse(inp([window(0)], [UNSUP]))
    assert any("preconditions" in x.en for x in r.decision.reasons)


# --- AC3: safety cannot be overridden -------------------------------------------------------------


def test_safety_level_survives_healthy_models():
    r = fuse(inp([window(0, 0, [safety("CRITICAL")])], [CLS_HEALTHY, DEG_LOW]))
    assert r.decision.health_state == H.CRITICAL
    assert r.decision.safety_constraints_applied == ["SAFE-TORQUE"]


@pytest.mark.parametrize("source", list(ProposalSource))
@pytest.mark.parametrize("proposed", [H.NORMAL, H.WATCH, H.WARNING, H.UNKNOWN])
def test_guard_never_lowers_a_safety_decision(source, proposed):
    d = fuse(inp([window(0, 0, [safety("WARNING")])])).decision
    assert guard(d, proposed, source).health_state == H.WARNING


def test_guard_llm_never_changes_and_model_only_raises_to_watch():
    d = fuse(inp([window(0)])).decision
    assert guard(d, H.CRITICAL, ProposalSource.LLM).health_state == H.NORMAL
    assert guard(d, H.CRITICAL, ProposalSource.MODEL).health_state == H.WATCH
    u = fuse(inp([])).decision
    assert guard(u, H.CRITICAL, ProposalSource.MODEL).health_state == H.UNKNOWN


def test_safety_is_never_graded_as_aging():
    hist = series(0.1, 90, hits=[safety("CRITICAL")])
    assert fuse(inp(hist)).decision.health_state == H.CRITICAL


# --- D-022: aging grading -------------------------------------------------------------------------


def test_slow_steady_aging_is_capped_at_watch_with_plan_recommendation():
    hist = series(0.1, 90, hits=[stat("WARNING", 9.0)])
    r = fuse(inp(hist))
    assert r.decision.health_state == H.WATCH
    assert r.aging["ST-TORQUE"].is_aging
    assert any("aging" in x.en for x in r.decision.reasons)
    (rec,) = r.recommendations
    assert rec.priority == RecommendationPriority.PLAN and "aging" in rec.action.en


@pytest.mark.parametrize(
    ("hist", "why"),
    [
        (series(1.0, 60, hits=[stat("WARNING", 12)]), "faster"),
        (series(0.1, 90, jump_at=86, hits=[stat("WARNING", 15)]), "Abrupt"),
        (series(0.1, 20, hits=[stat("WARNING", 6)]), "Installed only"),
    ],
)
def test_fast_abrupt_or_young_drift_keeps_its_level(hist, why):
    r = fuse(inp(hist))
    assert r.decision.health_state == H(hist[-1].level.value)
    assert why in r.aging["ST-TORQUE"].reason.en


def test_critical_is_never_lowered_by_aging_grading():  # D-040
    hist = series(0.1, 90, hits=[stat("CRITICAL", 30.0)])
    r = fuse(inp(hist))
    assert r.decision.health_state == H.CRITICAL
    assert "ST-TORQUE" not in r.aging


def test_accelerating_drift_is_not_aging():
    pts = [(d * 24.0, 0.05 * d) for d in range(60)] + [(d * 24.0, 3 + 0.3 * (d - 60)) for d in range(60, 75)]
    a = assess(pts)
    assert not a.is_aging


# --- AC4: recommendations reference evidence and versions ------------------------------------------


def test_recommendation_references_evidence_and_versions():
    r = fuse(inp([window(0, 30, [stat("CRITICAL", 30)])]))
    (rec,) = r.recommendations
    assert rec.priority == RecommendationPriority.IMMEDIATE
    assert set(rec.evidence_ids) <= {e.evidence_id for e in r.evidence} and rec.evidence_ids
    assert "evidence-fusion@" in rec.rationale.en and "pdm-rules@" in rec.rationale.en
    assert r.decision.meta.is_simulated


def test_normal_gives_no_recommendation():
    assert fuse(inp([window(0)])).recommendations == []


# --- golden cases on the replayed SIMULATED pipeline ----------------------------------------------


def _within(spans):
    return sum(
        r.decision.health_state.value in exp["allowed_health"] for _, exp, rs in spans for r in rs
    ), sum(len(rs) for _, _, rs in spans)


def test_golden_s03_normal_aging_stays_within_watch(replay):
    svc, machines = replay
    spans = graded(svc, machines, "S03")
    early = [r.decision.health_state for _, exp, rs in spans if exp["end_h"] <= 1440 for r in rs]
    late = [r.decision.health_state for _, exp, rs in spans if exp["start_h"] >= 1440 for r in rs]
    assert early and late
    # First 60 days: the Golden Case expects NORMAL; D-022 allows WATCH (CUSUM flags the slow shift).
    assert set(early) <= {H.NORMAL, H.WATCH}
    # Second 60 days: NORMAL or WATCH expected. Before D-022, 141 windows were WARNING and 4 CRITICAL.
    within = sum(x in (H.NORMAL, H.WATCH) for x in late)
    assert within / len(late) >= 0.98, (within, len(late))


@pytest.mark.parametrize("scenario", ["S01", "S04", "S07", "S19"])
def test_golden_faults_still_escalate_and_healthy_stays_normal(replay, scenario):
    svc, machines = replay
    spans = graded(svc, machines, scenario)
    ok, n = _within(spans)
    assert n and ok == n, (scenario, ok, n)


def test_golden_s11_partial_repair(replay):
    svc, machines = replay
    ok, n = _within(graded(svc, machines, "S11"))
    assert n and ok / n >= 0.9, (ok, n)


# --- D-043: safety check that cannot be evaluated is neither a violation nor normal ------------------


def _with_checks(w: WindowEvaluation, **checks) -> WindowEvaluation:
    from app.monitoring.schemas import SafetyStatus

    return w.model_copy(update={"safety_checks": {k: SafetyStatus(v) for k, v in checks.items()}})


def test_unmeasurable_safety_check_is_not_normal():
    from app.decision.schemas import QualityStatus
    from app.monitoring.schemas import SafetyStatus

    r = fuse(inp([_with_checks(window(0), **{"SF-TORQUE-LIMIT": "NOT_EVALUATED"})]))
    d = r.decision
    assert d.health_state == H.UNKNOWN  # never NORMAL: normal is not confirmed
    assert d.safety_status == SafetyStatus.NOT_EVALUATED
    assert d.safety_unevaluated == ["SF-TORQUE-LIMIT"]
    gap = next(x for x in r.evidence if x.evidence_id.startswith("SAFETY-GAP:"))
    assert not gap.applicable and gap.quality_status == QualityStatus.INVALID
    assert gap.proposed_severity is None  # no violation is claimed
    assert "无法评估" in d.reasons[-1].zh


def test_unmeasurable_safety_check_keeps_a_statistical_warning():
    hits = [stat("WARNING")]
    r = fuse(inp([_with_checks(window(0, hits=hits), **{"SF-TORQUE-LIMIT": "NOT_EVALUATED"})]))
    assert r.decision.health_state == H.WARNING
    assert r.decision.safety_unevaluated == ["SF-TORQUE-LIMIT"]


def test_confirmed_ok_and_violation_and_not_configured():
    from app.monitoring.schemas import SafetyStatus

    ok = fuse(inp([_with_checks(window(0), **{"SF-TORQUE-LIMIT": "CONFIRMED_OK"})])).decision
    assert (ok.health_state, ok.safety_status) == (H.NORMAL, SafetyStatus.CONFIRMED_OK)
    bad = fuse(inp([_with_checks(window(0, hits=[safety()]), **{"SF-TORQUE-LIMIT": "VIOLATED"})])).decision
    assert (bad.health_state, bad.safety_status) == (H.CRITICAL, SafetyStatus.VIOLATED)
    none = fuse(inp([window(0)])).decision
    assert (none.health_state, none.safety_status) == (H.NORMAL, SafetyStatus.NOT_CONFIGURED)


def test_evidence_object_carries_the_unified_fields():
    r = fuse(inp([window(0, hits=[safety()])]))
    ev = r.evidence[0]
    assert ev.evidence_type.value == "SAFETY" and ev.component_id == "C1"
    assert (ev.raw_value, ev.threshold) == (99.0, 90.0)
    assert ev.input_window_id.startswith("C1:") and ev.model_version and ev.evaluated_at
