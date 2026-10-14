# ruff: noqa: E501
"""The four checks a prediction configuration passes before it can be published (D-044).

1. data: the component's mapped signals return recent data from their sources.
2. compile: the pipeline is consistent with the component, its signals and the available models.
3. replay: the stored feature windows of the component are re-evaluated with the rules and references.
4. simulation: a synthetic scenario check of the decision logic (labelled SIMULATED, not plant evidence).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.schemas import TimeWindow
from app.datasource.query_service.sources import DataSourceRegistry
from app.datasource.sql import AdapterError
from app.decision import pipeline_config as pc
from app.decision.fleet import FleetHealthService
from app.decision.fusion import FusionInput, fuse
from app.decision.schemas import HealthState as H
from app.equipment.lifecycle import EquipmentStore
from app.monitoring.rules.engine import evaluate
from app.monitoring.schemas import (
    MonitoringLevel,
    RuleHit,
    RuleKind,
    SafetyStatus,
    WindowEvaluation,
)
from app.signals.registry import SignalConfigStore

_t = pc._t
LOOKBACK_H = 24  # a stopped machine has quiet stretches; the check wants any data in the last day


def data_check(session: Session, sources: DataSourceRegistry, component_id: str) -> pc.CheckResult:
    cfg = SignalConfigStore(session).current().content
    maps = [m for m in cfg.mappings if m.component_id == component_id]
    if not maps:
        return pc.CheckResult(
            name="data", ok=False, summary=_t("该部件没有信号映射", "The component has no signal mapping")
        )
    rows: dict[str, int] = {}
    problems: list[str] = []
    for m in maps:
        key = f"{m.data_source_id}/{m.device_id}/{m.key_name}"
        try:
            adapter = sources.adapter(m.data_source_id)
            meta = adapter.discover()
            if meta.latest_ts is None:
                rows[key] = 0
                continue
            win = TimeWindow(
                start=meta.latest_ts - timedelta(hours=LOOKBACK_H), end=meta.latest_ts + timedelta(seconds=1)
            )
            rows[key] = len(adapter.query_range(m.device_id, m.key_name, win, 50))
            if rows[key] == 0 and adapter.is_simulated and meta.earliest_ts is not None:
                # simulated scenarios end at different times; any data in the scenario will do
                rows[key] = len(adapter.query_incremental(m.device_id, m.key_name, meta.earliest_ts, 1))
        except (AdapterError, OSError, KeyError) as exc:
            rows[key] = 0
            problems.append(f"{key}: {type(exc).__name__}")
    empty = [k for k, n in rows.items() if n == 0]
    ok = not empty
    return pc.CheckResult(
        name="data", ok=ok,
        summary=_t(f"{len(maps)} 个映射均读到数据", f"All {len(maps)} mappings returned data") if ok
        else _t(f"{len(empty)} 个映射没有读到数据", f"{len(empty)} mapping(s) returned no data"),
        details={"rows_recent": rows, "problems": problems},
    )  # fmt: skip


def compile_check(session: Session, component_id: str, content: pc.ConfigContent) -> pc.CheckResult:
    result, _ = pc.compile_config(session, component_id, content)
    n_eff = sum(s.effective for s in result.stages)
    return pc.CheckResult(
        name="compile", ok=result.ok,
        summary=_t(f"编译通过：{n_eff}/{len(result.stages)} 个阶段将参与判定", f"Compiled: {n_eff}/{len(result.stages)} stages will take part")
        if result.ok else _t("编译失败，见问题列表", "Compile failed; see the issues"),
        details=result.model_dump(mode="json"),
    )  # fmt: skip


def replay_check(session: Session, component_id: str) -> pc.CheckResult:
    equipment = EquipmentStore(session)
    fleet = FleetHealthService(session)
    vectors = fleet.features.vectors(component_id)
    if not vectors:
        return pc.CheckResult(name="replay", ok=False, summary=_t(
            "该部件还没有历史特征窗口可回放（在线流水线尚未产生数据）",
            "No stored feature windows to replay (the online pipeline has not produced any yet)"))  # fmt: skip
    refs = {}
    for lc, ref_name in sorted({(v.lifecycle_id, v.feature_ref) for v in vectors}):
        if (ref := fleet.baselines.verified(component_id, lc, ref_name)) is not None:
            refs[lc] = ref
    if not refs:
        return pc.CheckResult(name="replay", ok=False, summary=_t(
            "没有工程师确认的健康参考，无法回放判定", "No verified healthy reference; the replay cannot grade"))  # fmt: skip
    evals = evaluate(vectors, refs, fleet.config.rules, fleet.settings.disabled(),
                     limits=equipment.torque_limits(), rules_version=fleet.rules_version())  # fmt: skip
    graded = [e for e in evals if e.evaluated]
    levels: dict[str, int] = {}
    for e in graded:
        levels[e.level.value] = levels.get(e.level.value, 0) + 1
    ok = bool(graded)
    return pc.CheckResult(
        name="replay", ok=ok,
        summary=_t(f"回放 {len(vectors)} 个窗口，{len(graded)} 个已评估", f"Replayed {len(vectors)} windows, {len(graded)} evaluated")
        if ok else _t("没有任何窗口可被评估", "No window could be evaluated"),
        details={"windows": len(vectors), "evaluated": len(graded), "levels": levels},
    )  # fmt: skip


def _win(hits=(), checks=None, level=MonitoringLevel.NORMAL) -> WindowEvaluation:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    return WindowEvaluation(
        component_id="SIM", lifecycle_id="SIM-LC", window=TimeWindow(start=t0, end=t0 + timedelta(hours=1)),
        feature_ref="sim@1", level=level, evaluated=True, hits=list(hits), statistics={}, not_evaluated=[],
        safety_checks=checks or {}, rules_version="sim", is_simulated=True,
    )  # fmt: skip


def simulation_check(component_type) -> pc.CheckResult:
    """Synthetic windows with known right answers run through the decision logic. It says nothing about
    this plant's data; it shows the logic behaves as specified for this component type."""

    def run(w):
        return fuse(FusionInput("SIM", component_type, "SIM-LC", None, w, [w])).decision

    def hit(kind, level, rid):
        return RuleHit(rule_id=rid, kind=kind, level=level, feature="f", value=9.0, threshold=1.0)

    ok_checks = {"SF-X": SafetyStatus.CONFIRMED_OK}
    cases = {
        "healthy_is_normal": run(_win(checks=ok_checks)).health_state == H.NORMAL,
        "critical_drift_is_critical": run(
            _win([hit(RuleKind.STATISTICAL, MonitoringLevel.CRITICAL, "ST-X")], ok_checks, MonitoringLevel.CRITICAL)
        ).health_state == H.CRITICAL,
        "safety_violation_keeps_its_level": run(
            _win([hit(RuleKind.SAFETY, MonitoringLevel.CRITICAL, "SF-X")], {"SF-X": SafetyStatus.VIOLATED}, MonitoringLevel.CRITICAL)
        ).health_state == H.CRITICAL,
        "unmeasurable_safety_is_not_normal": (
            lambda d: d.health_state == H.UNKNOWN and d.safety_status == SafetyStatus.NOT_EVALUATED
        )(run(_win(checks={"SF-X": SafetyStatus.NOT_EVALUATED}))),
    }  # fmt: skip
    ok = all(cases.values())
    return pc.CheckResult(
        name="simulation", ok=ok,
        summary=_t("合成场景检查通过（仿真，不代表现场数据）", "Synthetic scenario check passed (simulated; not plant evidence)")
        if ok else _t("合成场景检查未通过", "Synthetic scenario check failed"),
        details={"simulated": True, "cases": cases},
    )  # fmt: skip


def run_all(
    session: Session, sources: DataSourceRegistry, config: pc.PredictionConfig
) -> list[pc.CheckResult]:
    comp = next(c for c in EquipmentStore(session).components() if c.component_id == config.component_id)
    return [
        data_check(session, sources, config.component_id),
        compile_check(session, config.component_id, config.content),
        replay_check(session, config.component_id),
        simulation_check(comp.type),
    ]
