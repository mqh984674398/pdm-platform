# ruff: noqa: E501
"""Component health for the dashboard (T020, L6-04): rules on stored features, decided per component.

Health is an output of the rule evaluation and is never stored as a label. For each component the
rules run on its stored feature vectors against each lifecycle's verified healthy reference (the same
call as ``POST /api/alarms/evaluate``, without syncing alarms). The current state comes from the
newest window of the active lifecycle:

- UNKNOWN when the component has no feature windows, its installation has no verified reference, a
  post-maintenance validation is still running, no window could be evaluated, or the newest
  evaluated window is more than ``STALE_HOURS`` older than the machine's newest window (no usable
  data for this component);
- otherwise the level of the newest evaluated window (NORMAL, WATCH, WARNING, CRITICAL).

``as_of`` is relative to the machine's own newest data because simulated scenarios lie in the past.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.schemas import LocalizedText, ResultMeta, TimeWindow
from app.decision.config import active as active_config
from app.decision.fusion import FusionInput, FusionResult, Preconditions, fuse, recommend
from app.decision.pipeline_config import PredictionConfig, PredictionConfigStore, RelationType
from app.decision.schemas import (
    CommonCause,
    ComponentHealthReport,
    Decision,
    Evidence,
    EvidenceSource,
    EvidenceType,
    FleetComponent,
    FleetMachine,
    FleetOverview,
    HealthState,
    HealthTrend,
    RelatedStatus,
    TrendPoint,
)
from app.equipment.lifecycle import EquipmentStore
from app.equipment.maintenance import MaintenanceService
from app.equipment.maintenance_impact.service import ImpactService
from app.equipment.schemas import ComponentInstance, LifecycleStatus, MaintenanceWorkflowState
from app.monitoring.alarms.service import OPEN, AlarmService
from app.monitoring.anomaly import t2 as t2mod
from app.monitoring.baselines.verified import BaselineService
from app.monitoring.features.definitions import FEATURE_SETS
from app.monitoring.features.store import FeatureStore
from app.monitoring.rules.definitions import DEFAULT_RULES
from app.monitoring.rules.engine import component_type, evaluate
from app.monitoring.rules.settings import RuleSettings
from app.monitoring.schemas import Baseline, RuleKind, WindowEvaluation
from app.signals.registry import SignalConfigStore

STALE_HOURS = 24.0
VALIDATING = {
    MaintenanceWorkflowState.MAINTENANCE_EVENT,
    MaintenanceWorkflowState.STABILIZATION,
    MaintenanceWorkflowState.POST_MAINTENANCE_VALIDATION,
}
H = HealthState
BASIS = LocalizedText(
    zh="健康状态由统计与安全规则（{rules}）对照工程师确认的健康参考计算得出；演示数据均为模拟数据。",
    en="Health is computed by the statistical and safety rules ({rules}) against the "
    "engineer-verified healthy reference; all demo data is simulated.",
)


def _t(zh: str, en: str) -> LocalizedText:
    return LocalizedText(zh=zh, en=en)


NO_TELEMETRY = _t("暂无遥测特征数据", "No telemetry features yet")
NO_REFERENCE = _t(
    "当前安装尚无工程师确认的健康参考", "No verified healthy reference for the current installation"
)
VALIDATION = _t("维护后验证进行中，暂不给出结论", "Post-maintenance validation in progress; no verdict yet")
NOT_EVALUATED = _t("最新窗口数据不足，无法评估", "Not enough data in the newest window to evaluate")
NORMAL = _t("所有规则均在健康参考范围内", "All rules within the verified healthy reference")


def _stale(hours: float) -> LocalizedText:
    return _t(f"已 {hours:.0f} 小时没有可评估的数据", f"No evaluable data for {hours:.0f} h")


def _hit_text(e: WindowEvaluation) -> LocalizedText:
    rules = {r.rule_id: r for r in DEFAULT_RULES.rules}
    parts_zh, parts_en = [], []
    for h in sorted(e.hits, key=lambda h: -h.value / (h.threshold or 1)):
        desc = rules[h.rule_id].description if h.rule_id in rules else _t(h.rule_id, h.rule_id)
        cusum = h.basis == "cusum"
        held = h.value < h.threshold
        zh_v = f"{'CUSUM 累积量' if cusum else '数值' if h.basis == 'raw' else '持续偏差'} {h.value:.2f}"
        en_v = (
            f"{'CUSUM' if cusum else 'value' if h.basis == 'raw' else 'persistent deviation'} {h.value:.2f}"
        )
        zh_t = f"{h.level.value} 阈值 {h.threshold:g}{'，回落后保持中' if held else ''}"
        en_t = f"{h.level.value} threshold {h.threshold:g}{', held after dropping' if held else ''}"
        parts_zh.append(f"{h.rule_id}：{desc.zh}（{zh_v}，{zh_t}）")
        parts_en.append(f"{h.rule_id}: {desc.en} ({en_v}, {en_t})")
    return _t("；".join(parts_zh), "; ".join(parts_en))


def _join(reasons: Sequence[LocalizedText]) -> LocalizedText:
    return _t("；".join(r.zh for r in reasons), "; ".join(r.en for r in reasons))


class _Assessment:
    def __init__(
        self,
        health: HealthState,
        reason: LocalizedText,
        latest: WindowEvaluation | None,
        fusion: FusionResult | None = None,
    ):
        self.health, self.reason, self.latest, self.fusion = health, reason, latest, fusion


class FleetHealthService:
    def __init__(self, session: Session):
        self.session = session
        self.equipment = EquipmentStore(session)
        self.features = FeatureStore(session)
        self.baselines = BaselineService(session)
        self.maintenance = MaintenanceService(session)
        self.alarms = AlarmService(session)
        self.settings = RuleSettings(session)
        self.config = active_config(session)
        self.pcfg = PredictionConfigStore(session)

    # --- evaluation -----------------------------------------------------------------------------

    def rules_version(self) -> str:
        """Rule set in force (registry champion or default) plus the count of enable/disable changes."""
        return f"{self.config.rules.ref}+{self.settings.config_version().rsplit('+', 1)[1]}"

    def _evaluate(self, component_id: str) -> tuple[list[WindowEvaluation], dict[str, Baseline]]:
        vectors = self.features.vectors(component_id)
        refs: dict[str, Baseline] = {}
        for lc, ref_name in sorted({(v.lifecycle_id, v.feature_ref) for v in vectors}):
            ref = self.baselines.verified(component_id, lc, ref_name)
            if ref is not None:
                refs[lc] = ref
        evals = evaluate(
            vectors,
            refs,
            self.config.rules,
            self.settings.disabled(),
            limits=self.equipment.torque_limits(),
            rules_version=self.rules_version(),
        )
        return sorted(evals, key=lambda e: e.window.end), refs

    def _t2(
        self,
        cfg: PredictionConfig | None,
        component_id: str,
        lifecycle_id: str,
        ref: Baseline,
        latest: WindowEvaluation,
    ) -> list[t2mod.T2Finding]:
        """Hotelling T² for the newest windows; only when the active configuration enables it (D-045)."""
        if cfg is None or not any(
            st.algorithm == "mahalanobis-t2" and st.enabled for st in cfg.content.pipeline
        ):
            return []
        ctype = component_type(latest.feature_ref)
        feats = []
        for r in self.config.rules.rules:
            if r.kind == RuleKind.STATISTICAL and ctype in r.component_types:
                f = next((x for x in r.features if x in ref.stats), None)
                if f and f not in feats:
                    feats.append(f)
        vs = [
            v for v in self.features.vectors(component_id, latest.feature_ref, lifecycle_id)
            if v.window.end <= latest.window.end
        ]  # fmt: skip
        reference = [v for v in vs if ref.window.start <= v.window.start and v.window.end <= ref.window.end]
        return [t2mod.assess(reference, vs, feats)]

    def _assess(
        self,
        component_id: str,
        evals: Sequence[WindowEvaluation],
        refs: dict[str, Baseline],
        as_of: datetime | None,
    ) -> _Assessment:
        lcs = self.equipment.lifecycles(component_id)
        active = next((lc for lc in lcs if lc.status == LifecycleStatus.ACTIVE), None)
        mine = [e for e in evals if active and e.lifecycle_id == active.lifecycle_id]
        if not mine:
            return _Assessment(H.UNKNOWN, NO_TELEMETRY if not evals else NO_REFERENCE, None)
        latest = mine[-1]
        if active.lifecycle_id not in refs:
            return _Assessment(H.UNKNOWN, NO_REFERENCE, latest)
        open_wf = [w for w in self.maintenance.workflows(component_id) if not w.superseded_by]
        if open_wf and open_wf[-1].state in VALIDATING:
            return _Assessment(H.UNKNOWN, VALIDATION, latest)
        usable = [e for e in mine if e.evaluated]
        if not usable:
            return _Assessment(H.UNKNOWN, NOT_EVALUATED, latest)
        latest = usable[-1]  # a window in an unknown regime does not hide the last evaluated one
        stale = None
        if as_of is not None:
            gap = (as_of - latest.window.end).total_seconds() / 3600
            if gap > STALE_HOURS:
                stale = gap
        comp = self.equipment.component(component_id)
        cfg = self.pcfg.active(component_id)
        result = fuse(
            FusionInput(
                component_id=component_id,
                component_type=comp.type,
                lifecycle_id=active.lifecycle_id,
                installed_at=active.installed_at,
                evaluation=latest,
                history=mine,
                pre=Preconditions(stale_hours=stale),
                is_simulated=self.equipment.is_simulated(component_id),
                anomalies=self._t2(cfg, component_id, active.lifecycle_id, refs[active.lifecycle_id], latest),
                allowed=frozenset(cfg.content.criteria.allowed_evidence_types) if cfg else None,
            ),
            self.config.policy,
        )
        d = result.decision
        reason = NORMAL if d.health_state == H.NORMAL else _join(d.reasons)
        return _Assessment(d.health_state, reason, latest, result)

    def window_decisions(self, component_id: str) -> list[FusionResult]:
        """Fused decision for every evaluated window, using only the history up to that window."""
        comp = self.equipment.component(component_id)
        evals, refs = self._evaluate(component_id)
        lcs = {lc.lifecycle_id: lc for lc in self.equipment.lifecycles(component_id)}
        sim = self.equipment.is_simulated(component_id)
        out, seen = [], {}
        for e in evals:
            hist = seen.setdefault(e.lifecycle_id, [])
            hist.append(e)
            if not e.evaluated or e.lifecycle_id not in refs:
                continue
            lc = lcs.get(e.lifecycle_id)
            inp = FusionInput(
                component_id,
                comp.type,
                e.lifecycle_id,
                lc.installed_at if lc else None,
                e,
                list(hist),
                is_simulated=sim,
            )
            out.append(fuse(inp, self.config.policy))
        return out

    def _trend(self, component: ComponentInstance, evals: Sequence[WindowEvaluation]) -> list[HealthTrend]:
        out = []
        for r in self.config.rules.rules:
            if r.kind != RuleKind.STATISTICAL or component.type not in r.component_types:
                continue
            pts = [
                TrendPoint(ts=e.window.end, value=e.statistics[f"{r.rule_id}:persistent"])
                for e in evals
                if f"{r.rule_id}:persistent" in e.statistics
            ]
            feature = next(
                (h.feature for e in evals for h in e.hits if h.rule_id == r.rule_id), r.features[0]
            )
            if pts:
                out.append(
                    HealthTrend(
                        rule_id=r.rule_id,
                        name=r.description,
                        feature=feature,
                        watch=r.watch,
                        warning=r.warning,
                        critical=r.critical,
                        points=pts,
                    )
                )
        return out

    # --- views ----------------------------------------------------------------------------------

    def _relation_causes(self, health: dict[str, HealthState]) -> dict[str, CommonCause]:
        """Common causes from the active configurations' relationships (D-045), among known components."""
        out: dict[str, CommonCause] = {}
        for cid in sorted(health):
            cfg = self.pcfg.active(cid)
            rel = cfg.content.relationship if cfg else None
            if (
                rel is None
                or rel.type == RelationType.INDEPENDENT
                or not (rel.affects_common_cause and rel.members)
            ):
                continue
            bad = sorted(c for c in [cid, *rel.members] if health.get(c) in ABNORMAL)
            if len(bad) < 2 or cid not in bad:
                continue
            where = RELATION_NOTES[rel.type]
            names = "、".join(bad)
            cause = CommonCause(
                drive_chain_id=f"{rel.type.value}:{cid}",
                component_ids=bad,
                note=_t(
                    f"{names} 存在“{where[0]}”关系且同时异常：优先检查{where[1]}，再判断是否为各部件自身问题。",
                    f"{', '.join(bad)} are related ({where[2]}) and abnormal at the same time: check "
                    f"{where[3]} before treating it as a fault of each component.",
                ),
            )
            for b in bad:
                out.setdefault(b, cause)
        return out

    def overview(self) -> FleetOverview:
        signals = SignalConfigStore(self.session).current().content
        by_component: dict[str, list[str]] = {}
        for m in signals.mappings:
            if m.component_id:
                by_component.setdefault(m.component_id, []).append(m.signal_id)
        defs = {s.signal_id: s for s in signals.signals}
        machines = []
        for m in self.equipment.machines():
            comps = self.equipment.components(m.machine_id)
            evaluated = {c.component_id: self._evaluate(c.component_id) for c in comps}
            ends = [e[-1].window.end for e, _ in evaluated.values() if e]
            as_of = max(ends) if ends else None
            rows = []
            for c in comps:
                evals, refs = evaluated[c.component_id]
                a = self._assess(c.component_id, evals, refs, as_of)
                open_alarms = [x for x in self.alarms.alarms(c.component_id) if x.status.value in OPEN]
                sids = by_component.get(c.component_id, c.signal_ids)
                rows.append(
                    FleetComponent(
                        component_id=c.component_id,
                        machine_id=c.machine_id,
                        type=c.type,
                        name=c.name,
                        drive_chain_id=c.drive_chain_id,
                        health=a.health,
                        reason=a.reason,
                        lifecycle_id=a.latest.lifecycle_id if a.latest else None,
                        last_window_end=a.latest.window.end if a.latest else None,
                        open_alarms=len(open_alarms),
                        lifecycles=self.equipment.lifecycles(c.component_id),
                        maintenance=self.maintenance.events(c.component_id),
                        signals=[defs[s] for s in sids if s in defs],
                        trend=self._trend(c, evals),
                        is_simulated=self.equipment.is_simulated(c.component_id),
                    )
                )
            causes = common_causes([(r.component_id, r.drive_chain_id, r.health) for r in rows])
            rows = [r.model_copy(update={"common_cause": causes.get(r.component_id)}) for r in rows]
            machines.append(
                FleetMachine(
                    machine_id=m.machine_id,
                    name=m.name,
                    line=m.line,
                    path=m.path,
                    as_of=as_of,
                    components=rows,
                    is_simulated=m.is_simulated,
                )
            )
        health = {r.component_id: r.health for m in machines for r in m.components}
        relation = self._relation_causes(health)
        machines = [
            m.model_copy(
                update={
                    "components": [
                        r.model_copy(update={"common_cause": r.common_cause or relation.get(r.component_id)})
                        for r in m.components
                    ]
                }
            )
            for m in machines
        ]
        version = self.rules_version()
        basis = _t(BASIS.zh.format(rules=version), BASIS.en.format(rules=version))
        return FleetOverview(
            machines=machines,
            health_basis=basis,
            rules_version=version,
            is_simulated=any(m.is_simulated for m in machines),
        )

    def report(self, component_id: str) -> ComponentHealthReport:
        comp = self.equipment.component(component_id)
        evals, refs = self._evaluate(component_id)
        ends = [
            e[-1].window.end
            for c in self.equipment.components(comp.machine_id)
            if (e := self._evaluate(c.component_id)[0])
        ]
        as_of = max(ends) if ends else None
        a = self._assess(component_id, evals, refs, as_of)
        sim = self.equipment.is_simulated(component_id)
        version = self.rules_version()
        latest = a.latest
        computed = as_of or datetime.now(UTC)
        window = latest.window if latest else TimeWindow(start=computed - timedelta(hours=1), end=computed)

        def meta(feature: str, w: TimeWindow, model: str = version) -> ResultMeta:
            return ResultMeta(
                model_version=model,
                feature_version=feature,
                config_version=version,
                computed_at=computed,
                data_window=w,
                is_simulated=sim,
            )

        feature_ref = latest.feature_ref if latest else component_type_ref(comp)
        evidence: list[Evidence] = []
        if latest:
            ref = refs.get(latest.lifecycle_id)
            if a.fusion is not None:
                evidence += [
                    x.model_copy(update={"baseline_version": ref.baseline_id})
                    if ref is not None and x.evidence_type == EvidenceType.STATISTICAL
                    else x
                    for x in a.fusion.evidence
                ]
            if ref is not None:
                evidence.append(
                    Evidence(
                        evidence_id=f"REF:{ref.baseline_id}",
                        component_id=component_id,
                        evidence_type=EvidenceType.CONTEXT,
                        source=EvidenceSource.STATISTIC,
                        result_ref=ref.baseline_id,
                        summary=_t(
                            f"健康参考 {ref.baseline_id}：{ref.window.start:%Y-%m-%d %H:%M} 至 "
                            f"{ref.window.end:%Y-%m-%d %H:%M}，由 {ref.verified_by} 确认",
                            f"Healthy reference {ref.baseline_id}: {ref.window.start:%Y-%m-%d %H:%M} to "
                            f"{ref.window.end:%Y-%m-%d %H:%M}, verified by {ref.verified_by}",
                        ),
                        eligible=True,
                        meta=ref.meta,
                    )
                )
        for al in self.alarms.alarms(component_id):
            if al.status.value not in OPEN:
                continue
            evidence.append(
                Evidence(
                    evidence_id=f"ALARM:{al.alarm_id}",
                    component_id=component_id,
                    evidence_type=EvidenceType.CONTEXT,
                    source=EvidenceSource.RULE,
                    result_ref=al.alarm_id,
                    summary=_t(
                        f"{al.severity.value} 告警（{al.rule_id}）：{al.message.zh}",
                        f"{al.severity.value} alarm ({al.rule_id}): {al.message.en}",
                    ),
                    eligible=True,
                    meta=meta(
                        feature_ref,
                        TimeWindow(
                            start=al.raised_at,
                            end=max(al.last_window_end or al.raised_at, al.raised_at + timedelta(seconds=1)),
                        ),
                    ),
                )
            )
        impacts = ImpactService(self.session)
        for wf in self.maintenance.workflows(component_id):
            imp = impacts.impact(wf.workflow_id)
            if imp is None:
                continue
            evidence.append(
                Evidence(
                    evidence_id=f"IMPACT:{wf.workflow_id}",
                    component_id=component_id,
                    evidence_type=EvidenceType.CONTEXT,
                    source=EvidenceSource.MAINTENANCE,
                    result_ref=wf.workflow_id,
                    summary=_t(
                        f"维护效果 {imp.outcome.value}：{imp.reason.zh}",
                        f"Maintenance impact {imp.outcome.value}: {imp.reason.en}",
                    ),
                    eligible=True,
                    meta=meta(feature_ref, imp.post, "maintenance-impact@1.0.0"),
                )
            )
        ids = [e.evidence_id for e in evidence]
        if a.fusion is not None and a.health == a.fusion.decision.health_state:
            decision = a.fusion.decision.model_copy(update={"evidence_ids": ids})
            recommendations = a.fusion.recommendations
        else:
            decision = Decision(
                decision_id=f"HD-{component_id}-{window.end:%Y%m%dT%H%M%SZ}",
                component_id=component_id,
                lifecycle_id=latest.lifecycle_id if latest else "",
                health_state=a.health,
                reasons=[a.reason],
                evidence_ids=ids,
                meta=meta(feature_ref, window),
            )
            recommendations = recommend(decision, comp.type, evidence, {})
        cause = None
        if comp.drive_chain_id:
            peers = [
                c
                for c in self.equipment.components(comp.machine_id)
                if c.drive_chain_id == comp.drive_chain_id
            ]
            states = [
                (
                    c.component_id,
                    c.drive_chain_id,
                    a.health
                    if c.component_id == component_id
                    else self._assess(c.component_id, *self._evaluate(c.component_id), as_of).health,
                )
                for c in peers
            ]
            cause = common_causes(states).get(component_id)
        cfg = self.pcfg.active(component_id)
        related: list[RelatedStatus] = []
        if cfg and cfg.content.relationship.members:
            rel = cfg.content.relationship
            others = {
                m: self._assess(m, *self._evaluate(m), as_of).health
                for m in rel.members
                if any(c.component_id == m for c in self.equipment.components())
            }
            if cause is None and rel.affects_common_cause:
                cause = self._relation_causes({component_id: a.health, **others}).get(component_id)
            if rel.affects_status_display:
                related = [
                    RelatedStatus(component_id=m, relation=rel.type.value, health=h)
                    for m, h in others.items()
                ]
        return ComponentHealthReport(
            decision=decision,
            evidence=evidence,
            recommendations=recommendations,
            common_cause=cause,
            is_simulated=sim,
            config_version=cfg.config_id if cfg else None,
            display=cfg.content.display if cfg else None,
            related=related,
        )


ABNORMAL = (HealthState.WARNING, HealthState.CRITICAL)
# relation -> (zh name, zh what to check, en name, en what to check)
RELATION_NOTES = {
    RelationType.SHARED_DRIVETRAIN: (
        "共用传动链",
        "共用的传动链（联轴器、皮带、导轨、润滑）",
        "shared drivetrain",
        "the shared drivetrain",
    ),
    RelationType.MECHANICAL_DEPENDENCY: (
        "机械依赖",
        "相互之间的机械连接与受力",
        "mechanical dependency",
        "the mechanical coupling between them",
    ),
    RelationType.SHARED_SIGNAL: (
        "共用信号",
        "共用的传感器与信号",
        "shared signal",
        "the shared sensor and signal",
    ),
}


def common_causes(
    components: Sequence[tuple[str, str | None, HealthState]],
) -> dict[str, CommonCause]:
    """component id → shared drive-chain cause, for chains with two or more WARNING/CRITICAL members."""
    chains: dict[str, list[str]] = {}
    for cid, chain, health in components:
        if chain and health in ABNORMAL:
            chains.setdefault(chain, []).append(cid)
    out: dict[str, CommonCause] = {}
    for chain, ids in chains.items():
        if len(ids) < 2:
            continue
        names = "、".join(ids)
        cause = CommonCause(
            drive_chain_id=chain,
            component_ids=sorted(ids),
            note=_t(
                f"共用传动链 {chain} 上的 {names} 同时异常：优先检查传动链（联轴器、皮带、导轨与润滑），"
                "再判断是否为各部件自身磨损。",
                f"{', '.join(ids)} on shared drive chain {chain} are abnormal at the same time: check "
                "the drive chain (coupling, belt, guides, lubrication) before treating it as wear of "
                "each component.",
            ),
        )
        for cid in ids:
            out[cid] = cause
    return out


def component_type_ref(comp: ComponentInstance) -> str:
    fs = FEATURE_SETS.get(comp.type)
    return f"{fs.feature_set}@{fs.version}" if fs else "no-feature-set"
