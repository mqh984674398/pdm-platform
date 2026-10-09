"""Evidence fusion and maintenance decisions (T024, L6-01..05, D-022).

Inputs per component and window: the rule evaluation (statistical and safety hits), the rule history
of the current installation (for aging grading), routed prediction results, and the preconditions
the caller checked (reference verified, validation running, data stale). Output: one ``Decision``
with reasons and evidence, and the recommendations that follow from it.

Order of the rules, each explicit:

1. Preconditions. No evaluable window, no verified reference, validation running or stale data give
   UNKNOWN with the reason (abstention). No model output can turn UNKNOWN into a level.
2. Safety floor. The highest SAFETY rule level is a floor: nothing below may lower it (L6-03).
3. Statistical level. Each STATISTICAL hit keeps its level, except a hit whose rule history is a
   slow, steady drift consistent with the component's age, which is capped at WATCH (D-022, see
   ``aging``). Abrupt or accelerating drift keeps its level.
4. Model evidence. Typed results are read only through ``INTERPRETATION``; each kind maps to one
   direction (DEGRADED, HEALTHY, NEUTRAL) and nothing else. Unsupported, ineligible and failure
   probability results carry no direction. Models never raise a level above WATCH and never lower
   a safety level. When they disagree with the rules (or with each other) the result is WATCH with
   ``conflicting_evidence`` and the reason; rules alone decide WARNING and CRITICAL.
5. Final level = max(safety floor, fused statistical level).

The LLM takes no part: ``guard`` is the single place where any later proposal (model or LLM) may
adjust a decision, and it never goes below the safety floor or above the evidence-backed level.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from app.core.schemas import LocalizedText, ResultMeta, TimeWindow
from app.decision.aging import DEFAULT_POLICY, AgingAssessment, AgingPolicy, assess
from app.decision.schemas import (
    Decision,
    Evidence,
    EvidenceSource,
    HealthState,
    Recommendation,
    RecommendationPriority,
)
from app.equipment.schemas import ComponentType
from app.monitoring.alarms.service import evidence_id
from app.monitoring.schemas import RuleKind, WindowEvaluation
from app.prediction.schemas import (
    AnomalyScoreResult,
    ClassProbabilityResult,
    DegradationIndicatorResult,
    PredictionResult,
)

FUSION_VERSION = "evidence-fusion@1.0.0"
H = HealthState
ORDER = [H.NORMAL, H.WATCH, H.WARNING, H.CRITICAL]


def _t(zh: str, en: str) -> LocalizedText:
    return LocalizedText(zh=zh, en=en)


def _max(*levels: HealthState) -> HealthState:
    return max(levels, key=ORDER.index)


class Direction(StrEnum):
    DEGRADED = "DEGRADED"
    HEALTHY = "HEALTHY"
    NEUTRAL = "NEUTRAL"


# --- interpretation of typed model outputs (AC1) ------------------------------------------------

DEGRADATION_HIGH, DEGRADATION_LOW = 3.0, 1.0  # robust deviation from the verified reference
CLASS_HIGH, CLASS_LOW = 0.8, 0.2  # uncalibrated class score for "degraded"


def _degradation(r: DegradationIndicatorResult) -> Direction:
    v = r.value if r.higher_is_worse else -r.value
    return (
        Direction.DEGRADED
        if v >= DEGRADATION_HIGH
        else Direction.HEALTHY
        if v < DEGRADATION_LOW
        else Direction.NEUTRAL
    )


def _anomaly(r: AnomalyScoreResult) -> Direction:
    if r.threshold is None:
        return Direction.NEUTRAL  # a score without its threshold has no agreed reading
    return (
        Direction.DEGRADED
        if r.score >= r.threshold
        else Direction.HEALTHY
        if r.score < r.threshold / 2
        else Direction.NEUTRAL
    )


def _class(r: ClassProbabilityResult) -> Direction:
    p = r.probabilities.get("degraded")
    if p is None:
        return Direction.NEUTRAL
    return (
        Direction.DEGRADED if p >= CLASS_HIGH else Direction.HEALTHY if p <= CLASS_LOW else Direction.NEUTRAL
    )


INTERPRETATION: dict[str, Callable[..., Direction] | None] = {
    "degradation_indicator": _degradation,
    "anomaly_score": _anomaly,
    "class_probability": _class,
    # A failure probability is a lifecycle statement, not a health level; it is kept as evidence only.
    "failure_probability": None,
    "unsupported": None,
}


def interpret(r: PredictionResult) -> Direction | None:
    """Direction of one result, or None when it may not be used for health."""
    fn = INTERPRETATION.get(r.kind)
    return fn(r) if fn is not None else None


# --- inputs and outputs -------------------------------------------------------------------------


@dataclass
class Preconditions:
    reference_verified: bool = True
    validation_running: bool = False
    stale_hours: float | None = None  # gap to the machine's newest data when beyond the limit


@dataclass
class FusionInput:
    component_id: str
    component_type: ComponentType
    lifecycle_id: str
    installed_at: datetime | None
    evaluation: WindowEvaluation | None  # newest evaluated window of the installation
    history: Sequence[WindowEvaluation] = ()  # same installation, up to and including evaluation
    predictions: Sequence[PredictionResult] = ()
    pre: Preconditions = field(default_factory=Preconditions)
    is_simulated: bool = True


@dataclass
class FusionResult:
    decision: Decision
    evidence: list[Evidence]
    recommendations: list[Recommendation]
    aging: dict[str, AgingAssessment]


NO_EVALUATION = _t("没有可评估的特征窗口", "No evaluable feature window")
NO_REFERENCE = _t(
    "当前安装尚无工程师确认的健康参考", "No verified healthy reference for the current installation"
)
VALIDATION = _t("维护后验证进行中，暂不给出结论", "Post-maintenance validation in progress; no verdict yet")
ALL_NORMAL = _t("所有规则均在健康参考范围内", "All rules within the verified healthy reference")


def _stale(hours: float) -> LocalizedText:
    return _t(f"已 {hours:.0f} 小时没有可评估的数据", f"No evaluable data for {hours:.0f} h")


def _aging_points(inp: FusionInput, rule_id: str) -> list[tuple[float, float]]:
    key = f"{rule_id}:persistent"
    start = inp.installed_at or (inp.history[0].window.start if inp.history else None)
    if start is None:
        return []
    end = inp.evaluation.window.end if inp.evaluation else None
    return [
        ((e.window.end - start).total_seconds() / 3600, e.statistics[key])
        for e in inp.history
        if e.evaluated and key in e.statistics and (end is None or e.window.end <= end)
    ]


def fuse(inp: FusionInput, policy: AgingPolicy = DEFAULT_POLICY) -> FusionResult:
    e = inp.evaluation
    reasons: list[LocalizedText] = []
    evidence: list[Evidence] = []
    safety: list[str] = []
    aging: dict[str, AgingAssessment] = {}
    conflict = False

    def meta(model: str) -> ResultMeta:
        return ResultMeta(
            model_version=model,
            feature_version=e.feature_ref,
            config_version=f"{e.rules_version}; {FUSION_VERSION}; {policy.version}",
            computed_at=e.window.end,
            data_window=e.window,
            is_simulated=inp.is_simulated,
        )

    # 1. preconditions -> abstain
    abstain = None
    if e is None or not e.evaluated:
        abstain = NO_EVALUATION
    elif not inp.pre.reference_verified:
        abstain = NO_REFERENCE
    elif inp.pre.validation_running:
        abstain = VALIDATION
    elif inp.pre.stale_hours is not None:
        abstain = _stale(inp.pre.stale_hours)
    if abstain is not None:
        return _abstain(inp, abstain)

    # 2. safety floor; 3. statistical level with aging grading
    floor = H.NORMAL
    stat = H.NORMAL
    for h in e.hits:
        lvl = H(h.level.value)
        eid = evidence_id(h.rule_id, e)
        if h.kind == RuleKind.SAFETY:
            floor = _max(floor, lvl)
            safety.append(h.rule_id)
            reasons.append(
                _t(
                    f"安全规则 {h.rule_id} 触发 {lvl.value}（数值 {h.value:.2f}，阈值 {h.threshold:g}），"
                    "模型不能降低",
                    f"Safety rule {h.rule_id} at {lvl.value} (value {h.value:.2f}, limit {h.threshold:g}); "
                    "no model can lower it",
                )
            )
            evidence.append(
                Evidence(
                    evidence_id=eid,
                    source=EvidenceSource.RULE,
                    result_ref=eid,
                    summary=reasons[-1],
                    eligible=True,
                    meta=meta(e.rules_version),
                )
            )
            continue
        graded = lvl
        if _max(lvl, H.WATCH) != H.WATCH:
            a = aging[h.rule_id] = assess(_aging_points(inp, h.rule_id), policy)
            if a.is_aging:
                graded = H.WATCH
                aid = f"AGING:{h.rule_id}:{e.component_id}:{e.window.start.isoformat()}"
                evidence.append(
                    Evidence(
                        evidence_id=aid,
                        source=EvidenceSource.STATISTIC,
                        result_ref=eid,
                        summary=a.reason,
                        eligible=True,
                        meta=meta(policy.version),
                    )
                )
        stat = _max(stat, graded)
        txt = _t(
            f"统计规则 {h.rule_id}：{h.feature} 偏离健康参考 {h.value:.2f}"
            f"（{lvl.value} 阈值 {h.threshold:g}）",
            f"Statistical rule {h.rule_id}: {h.feature} {h.value:.2f} from the healthy reference "
            f"({lvl.value} threshold {h.threshold:g})",
        )
        if graded != lvl:
            txt = _t(f"{txt.zh}；{aging[h.rule_id].reason.zh}", f"{txt.en}; {aging[h.rule_id].reason.en}")
        reasons.append(txt)
        evidence.append(
            Evidence(
                evidence_id=eid,
                source=EvidenceSource.STATISTIC,
                result_ref=eid,
                summary=txt,
                eligible=True,
                meta=meta(e.rules_version),
            )
        )

    # 4. model evidence through the interpretation table
    directions: list[Direction] = []
    for p in inp.predictions:
        d = interpret(p)
        pid = f"PRED:{p.operator_id}:{e.component_id}:{e.window.start.isoformat()}"
        usable = d is not None and p.lifecycle_id == inp.lifecycle_id
        if usable:
            directions.append(d)
            txt = _t(
                f"{p.operator_id}（{p.kind}）判读为 {d.value}",
                f"{p.operator_id} ({p.kind}) read as {d.value}",
            )
        elif p.kind == "unsupported":
            txt = _t(f"{p.operator_id} 不可用：{p.detail.zh}", f"{p.operator_id} not usable: {p.detail.en}")
        else:
            txt = _t(
                f"{p.operator_id}（{p.kind}）不参与健康判定",
                f"{p.operator_id} ({p.kind}) not used for health",
            )
        evidence.append(
            Evidence(
                evidence_id=pid,
                source=EvidenceSource.MODEL,
                result_ref=p.operator_id,
                summary=txt,
                eligible=usable,
                meta=p.meta,
            )
        )
    deg = Direction.DEGRADED in directions
    ok = Direction.HEALTHY in directions
    if deg and ok:
        conflict = True
        reasons.append(_t("模型结论互相矛盾", "Model outputs disagree with each other"))
        stat = _max(stat, H.WATCH)  # no net model direction: rules keep any higher level
    elif deg and stat == H.NORMAL:
        conflict = True
        stat = H.WATCH
        reasons.append(
            _t(
                "模型提示劣化而规则正常，按“关注”复核",
                "Models indicate degradation while rules are normal; WATCH for review",
            )
        )
    elif ok and _max(stat, H.WATCH) != H.WATCH:
        conflict = True
        stat = H.WATCH
        reasons.append(
            _t(
                "统计规则偏高而模型判读为健康，证据冲突，按“关注”复核",
                "Statistical rules are high while models read healthy; conflicting evidence, "
                "WATCH for review",
            )
        )
    elif inp.predictions and not directions:
        reasons.append(
            _t("模型分析均不满足使用条件，仅依据规则", "No model analysis met its preconditions; rules only")
        )

    # 5. final
    level = _max(floor, stat)
    if not reasons:
        reasons.append(ALL_NORMAL)
    decision = Decision(
        decision_id=f"HD-{e.component_id}-{e.window.end:%Y%m%dT%H%M%SZ}",
        component_id=e.component_id,
        lifecycle_id=e.lifecycle_id,
        health_state=level,
        reasons=reasons,
        evidence_ids=[x.evidence_id for x in evidence],
        safety_constraints_applied=safety,
        conflicting_evidence=conflict,
        meta=meta(FUSION_VERSION),
    )
    return FusionResult(decision, evidence, recommend(decision, inp.component_type, evidence, aging), aging)


def _abstain(inp: FusionInput, reason: LocalizedText) -> FusionResult:
    e = inp.evaluation
    end = e.window.end if e else datetime.now(UTC)
    window = e.window if e else TimeWindow(start=end - timedelta(hours=1), end=end)
    m = ResultMeta(
        model_version=FUSION_VERSION,
        feature_version=e.feature_ref if e else "none",
        config_version=e.rules_version if e else "none",
        computed_at=end,
        data_window=window,
        is_simulated=inp.is_simulated,
    )
    ev = Evidence(
        evidence_id=f"PRE:{inp.component_id}:{end.isoformat()}",
        source=EvidenceSource.DATA_QUALITY,
        result_ref=inp.lifecycle_id or inp.component_id,
        summary=reason,
        eligible=False,
        meta=m,
    )
    d = Decision(
        decision_id=f"HD-{inp.component_id}-{end:%Y%m%dT%H%M%SZ}",
        component_id=inp.component_id,
        lifecycle_id=inp.lifecycle_id,
        health_state=H.UNKNOWN,
        reasons=[reason],
        evidence_ids=[ev.evidence_id],
        meta=m,
    )
    return FusionResult(d, [ev], recommend(d, inp.component_type, [ev], {}), {})


# --- guard against later overrides (L6-03) ------------------------------------------------------


class ProposalSource(StrEnum):
    MODEL = "MODEL"
    LLM = "LLM"


def guard(decision: Decision, proposed: HealthState, source: ProposalSource) -> Decision:
    """The only way a later proposal (model or LLM) may touch a decision (L6-03, GEN-04).

    Nothing is ever lowered, so a safety level stands; UNKNOWN stays UNKNOWN; the LLM never changes the
    level; a model may raise NORMAL to WATCH (for review) and no further."""
    if source == ProposalSource.LLM or decision.health_state != H.NORMAL or proposed in (H.NORMAL, H.UNKNOWN):
        return decision
    return decision.model_copy(
        update={
            "health_state": H.WATCH,
            "conflicting_evidence": True,
            "reasons": [
                *decision.reasons,
                _t("模型建议复核，按“关注”处理", "A model proposed a review; WATCH"),
            ],
        }
    )


# --- recommendations (L6-05) --------------------------------------------------------------------

ACTIONS: dict[ComponentType, tuple[LocalizedText, LocalizedText]] = {
    ComponentType.BALL_SCREW: (
        _t(
            "检查润滑状态并安排丝杠预紧与磨损检查",
            "Check lubrication and schedule a preload and wear inspection",
        ),
        _t(
            "停机检查滚珠丝杠（润滑、异响、预紧、轴承）",
            "Stop and inspect the ball screw (lubrication, noise, preload, bearings)",
        ),
    ),
    ComponentType.PNEUMATIC_CYLINDER: (
        _t("检查气源压力、节流阀和密封件", "Check supply pressure, flow controls and seals"),
        _t("停机检查气缸（漏气、密封、导向）", "Stop and inspect the cylinder (leaks, seals, guides)"),
    ),
    ComponentType.LINEAR_MOTOR: (
        _t("检查电缆、编码器和伺服参数", "Check cabling, encoder and servo tuning"),
        _t(
            "停机检查直线电机（编码器、电缆、导轨）",
            "Stop and inspect the linear motor (encoder, cabling, rails)",
        ),
    ),
    ComponentType.VACUUM_CUP: (
        _t("检查吸盘磨损、过滤器和真空管路", "Check cup wear, filter and vacuum lines"),
        _t("停机更换或检查吸盘与真空发生器", "Stop and replace or inspect the cup and vacuum generator"),
    ),
}
GENERIC = (_t("安排检查", "Schedule an inspection"), _t("停机检查", "Stop and inspect"))


def recommend(
    d: Decision, ctype: ComponentType, evidence: Sequence[Evidence], aging: dict[str, AgingAssessment]
) -> list[Recommendation]:
    plan, stop = ACTIONS.get(ctype, GENERIC)
    ids = [x.evidence_id for x in evidence] or d.evidence_ids
    versions = f"{d.meta.model_version}; {d.meta.config_version}"
    rid = f"REC-{d.decision_id}"
    s = d.health_state
    if s == H.NORMAL:
        return []
    if s == H.UNKNOWN:
        action = _t(
            "先恢复可用证据（数据、健康参考或完成验证），再判断健康",
            "Restore usable evidence first (data, healthy reference or finished validation), "
            "then judge health",
        )
        prio = RecommendationPriority.INFO
    elif s == H.CRITICAL:
        action, prio = stop, RecommendationPriority.IMMEDIATE
    elif s == H.WARNING:
        action, prio = plan, RecommendationPriority.SOON
    elif any(a.is_aging for a in aging.values()) and not d.conflicting_evidence:
        action = _t(
            f"正常老化：在下次计划保养时{plan.zh}",
            f"Normal aging: at the next planned service, {plan.en[0].lower()}{plan.en[1:]}",
        )
        prio = RecommendationPriority.PLAN
    else:
        action, prio = plan, RecommendationPriority.PLAN
    rationale = _t(
        "；".join(r.zh for r in d.reasons) + f"（版本：{versions}）",
        "; ".join(r.en for r in d.reasons) + f" (versions: {versions})",
    )
    return [
        Recommendation(
            recommendation_id=rid,
            decision_id=d.decision_id,
            priority=prio,
            action=action,
            rationale=rationale,
            evidence_ids=ids,
        )
    ]
