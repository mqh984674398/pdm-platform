"""The 20 required simulated scenarios (REQUIREMENTS §14) and their Golden Cases.

Single source for scenario configs, metadata, and expectations. Generate with
``python -m app.simulation.scenarios`` and verify with ``python -m app.simulation.scenarios --verify``.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.schemas import LocalizedText
from app.decision.schemas import HealthState as H
from app.equipment.schemas import MaintenanceWorkflowState as W
from app.prediction.schemas import UnsupportedReason as U
from app.signals.schemas import QualityFlag as Q
from app.simulation.config import SimulationConfig
from app.simulation.demo_fleet import write_fleet
from app.simulation.generator import generate
from app.simulation.golden import DATA_DIR, Expectation, GoldenCase, ScenarioMeta
from app.simulation.studio_fixture import write_studio
from app.simulation.writer import read_text, update_manifest, write_dataset

D = 24.0  # hours per day
START = "2026-02-02T00:00:00Z"
KNOWN_REGIMES = ["R-A", "R-B"]
ALL = list(H)
OK = [H.NORMAL]
OK_OR_UNKNOWN = [H.NORMAL, H.UNKNOWN]
NOT_NORMAL = [H.WATCH, H.WARNING, H.CRITICAL]
DEGRADED = [H.WARNING, H.CRITICAL]


def L(zh: str, en: str) -> LocalizedText:
    return LocalizedText(zh=zh, en=en)


RECIPES = [
    {
        "recipe_id": "R-A",
        "servo_speed_rpm": 1500,
        "load_nm": 1.5,
        "linear_speed_mm_s": 400,
        "cycle_period_s": 6.0,
    },
    {
        "recipe_id": "R-B",
        "servo_speed_rpm": 3000,
        "load_nm": 2.5,
        "linear_speed_mm_s": 800,
        "cycle_period_s": 4.5,
        "pressure_factor": 1.05,
        "part_factor": 1.1,
    },
    {
        "recipe_id": "R-C",
        "servo_speed_rpm": 2200,
        "load_nm": 4.0,
        "linear_speed_mm_s": 600,
        "cycle_period_s": 5.0,
        "pressure_factor": 0.95,
        "part_factor": 0.9,
    },
    {
        "recipe_id": "R-X",
        "servo_speed_rpm": 4200,
        "load_nm": 6.0,
        "linear_speed_mm_s": 1100,
        "cycle_period_s": 3.5,
        "pressure_factor": 1.2,
        "part_factor": 1.3,
    },
]

COMPONENTS = {
    "BS1": {
        "type": "BALL_SCREW",
        "name": {"zh": "X轴滚珠丝杠", "en": "X-axis ball screw"},
        "drive_chain_id": "M01-DC1",
        "rated_torque_nm": 10.0,
    },
    "BS2": {
        "type": "BALL_SCREW",
        "name": {"zh": "Y轴滚珠丝杠", "en": "Y-axis ball screw"},
        "drive_chain_id": "M01-DC1",
        "rated_torque_nm": 10.0,
    },
    "LM1": {"type": "LINEAR_MOTOR", "name": {"zh": "传送直线电机", "en": "Transfer linear motor"}},
    "VC1": {"type": "VACUUM_CUP", "name": {"zh": "取料真空吸盘", "en": "Pick vacuum cup"}},
    "CY1": {"type": "PNEUMATIC_CYLINDER", "name": {"zh": "压紧气缸", "en": "Clamp cylinder"}},
}
SIGNALS = {
    "BS1": ["M01-BS1.speed", "M01-BS1.torque"],
    "BS2": ["M01-BS2.speed", "M01-BS2.torque"],
    "LM1": ["M01-LM1.speed"],
    "VC1": ["M01-VC1.release_time"],
    "CY1": ["M01-CY1.extend_time", "M01-CY1.retract_time"],
}


def key(component: str, suffix: str) -> str:
    return f"M01_{component}_{suffix}"


@dataclass
class Scenario:
    sid: str
    slug: str
    title: LocalizedText
    days: float
    components: list[str]
    observable: LocalizedText
    truth: LocalizedText
    response: LocalizedText
    abstention: list[LocalizedText]
    cases: list[tuple[str, LocalizedText, list[Expectation]]]  # (component, title, expectations)
    recipes: list[str] = field(default_factory=lambda: ["R-A", "R-B"])
    recipe_schedule: list[tuple[float, str]] = field(default_factory=list)
    windows_per_day: int = 4
    aging: list[dict[str, Any]] = field(default_factory=list)
    effects: list[dict[str, Any]] = field(default_factory=list)
    maintenance: list[dict[str, Any]] = field(default_factory=list)
    data_faults: list[dict[str, Any]] = field(default_factory=list)
    incomplete_ops: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[LocalizedText] = field(default_factory=list)

    @property
    def number(self) -> int:
        return int(self.sid[1:])

    @property
    def dataset_id(self) -> str:
        return f"{self.sid.lower()}_{self.slug}"

    @property
    def device(self) -> str:
        return f"SIM-{self.sid}"

    def config(self) -> SimulationConfig:
        used = set(self.recipes) | {r for _, r in self.recipe_schedule}
        faults = [f | {"device_id": self.device} for f in self.data_faults]
        return SimulationConfig.model_validate(
            {
                "dataset_id": self.dataset_id,
                "description": f"{self.sid} {self.title.en} (SIMULATED)",
                "seed": 5000 + self.number,
                "start": START,
                "duration_hours": self.days * D,
                "observation": {
                    "windows_per_day": self.windows_per_day,
                    "window_minutes": 2,
                    "servo_sample_s": 2.0,
                    "linear_sample_s": 2.0,
                    "idle_fraction": 0.08,
                    "stopped_fraction": 0.04,
                },
                "recipes": [r for r in RECIPES if r["recipe_id"] in used],
                "machines": [
                    {
                        "machine_id": "M01",
                        "device_id": self.device,
                        "name": {"zh": f"模拟设备 {self.sid}", "en": f"Simulated machine {self.sid}"},
                        "recipes": self.recipes,
                        "recipe_schedule": self.recipe_schedule,
                        "components": [
                            {"component_id": f"M01-{c}", **COMPONENTS[c]} for c in self.components
                        ],
                    }
                ],
                "aging": self.aging
                or [{"target": f"M01-{c}", "rate_per_1000h": 0.05} for c in self.components],
                "effects": self.effects,
                "maintenance": self.maintenance,
                "data_faults": faults,
                "incomplete_ops": self.incomplete_ops,
            }
        )

    def golden_cases(self) -> list[GoldenCase]:
        return [
            GoldenCase(
                case_id=f"GC-{self.sid}-{i + 1:02d}",
                scenario_id=self.sid,
                component_id=f"M01-{comp}",
                signal_ids=SIGNALS[comp],
                title=title,
                expectations=exps,
            )
            for i, (comp, title, exps) in enumerate(self.cases)
        ]

    def meta(self) -> ScenarioMeta:
        return ScenarioMeta(
            scenario_id=self.sid,
            slug=self.slug,
            title=self.title,
            seed=5000 + self.number,
            dataset_id=self.dataset_id,
            known_regimes=KNOWN_REGIMES if "R-C" not in self.recipes else [*KNOWN_REGIMES, "R-C"],
            expected_observable_behavior=self.observable,
            ground_truth=self.truth,
            expected_health_response=self.response,
            abstention_cases=self.abstention,
            limitations=self.limitations,
            golden_case_ids=[g.case_id for g in self.golden_cases()],
        )


def E(
    start_d: float,
    end_d: float,
    allowed: list[H],
    zh: str,
    en: str,
    flags: list[Q] | None = None,
    abstain: U | None = None,
    workflow: list[W] | None = None,
) -> Expectation:
    return Expectation(
        start_h=start_d * D,
        end_h=end_d * D,
        allowed_health=allowed,
        required_flags=flags or [],
        must_abstain=abstain,
        workflow=workflow,
        note=L(zh, en),
    )


NO_ABSTAIN = [
    L(
        "无强制弃权；空闲/停机窗口不评估健康状态。",
        "No mandatory abstention; idle/stopped windows are not assessed.",
    )
]
NO_WEAR_PROOF = L(
    "转矩升高只说明负载/摩擦变化，不能单独证明丝杠磨损。",
    "Higher torque indicates a load/friction change; it does not alone prove ball-screw wear.",
)
NO_RUL = L(
    "无失效数据：失效概率/RUL 必须返回不支持（NO_FAILURE_EVIDENCE）。",
    "No failure data: failure probability/RUL must return unsupported (NO_FAILURE_EVIDENCE).",
)
POST_OK = [W.MAINTENANCE_EVENT, W.STABILIZATION, W.POST_MAINTENANCE_VALIDATION, W.NORMAL_MONITORING]
POST_REVIEW = [W.MAINTENANCE_EVENT, W.STABILIZATION, W.POST_MAINTENANCE_VALIDATION, W.REVIEW_REQUIRED]


def scenarios() -> list[Scenario]:
    S: list[Scenario] = []
    S.append(
        Scenario(
            "S01",
            "healthy",
            L("稳定健康运行", "Stable healthy operation"),
            14,
            ["BS1", "LM1", "VC1", "CY1"],
            L(
                "所有信号在各自工况内平稳，仅有噪声与极轻微老化。",
                "All signals stable within their regimes; only noise and negligible aging.",
            ),
            L("无故障注入；老化率 0.05/1000h。", "No faults injected; aging rate 0.05/1000h."),
            L("全部部件 NORMAL，不应产生报警。", "All components NORMAL; no alarms."),
            [*NO_ABSTAIN, NO_RUL],
            [
                (
                    c,
                    L(f"{c} 健康基线", f"{c} healthy baseline"),
                    [E(0, 14, OK, "全程正常", "Normal throughout")],
                )
                for c in ["BS1", "LM1", "VC1", "CY1"]
            ],
        )
    )
    S.append(
        Scenario(
            "S02",
            "multi_regime",
            L("多工况运行", "Multiple operating regimes"),
            14,
            ["BS1", "LM1", "VC1", "CY1"],
            L(
                "转速、转矩、动作时间随配方 R-A/R-B/R-C 明显分层。",
                "Speed, torque, and durations shift by recipe R-A/R-B/R-C.",
            ),
            L("三种已知配方随机切换；无故障。", "Three known recipes switch randomly; no faults."),
            L(
                "工况归一化后全部 NORMAL；不按工况区分会误报。",
                "NORMAL after regime normalization; regime-unaware checks would false-alarm.",
            ),
            NO_ABSTAIN,
            [
                (
                    "BS1",
                    L("转矩随工况变化不应报警", "Regime-driven torque change must not alarm"),
                    [E(0, 14, OK, "工况变化不是劣化", "Regime change is not degradation")],
                ),
                (
                    "CY1",
                    L("气压工况影响动作时间", "Supply-pressure regime affects durations"),
                    [E(0, 14, OK, "工况变化不是劣化", "Regime change is not degradation")],
                ),
            ],
            recipes=["R-A", "R-B", "R-C"],
        )
    )
    S.append(
        Scenario(
            "S03",
            "normal_aging",
            L("正常长期老化", "Normal long-term aging"),
            120,
            ["BS1", "CY1"],
            L(
                "相对冻结的健康基准，转矩与伸出时间缓慢单调上升。",
                "Torque and extension time rise slowly and monotonically against the frozen healthy reference.",
            ),
            L(
                "丝杠磨损 0.06/1000h，气缸 0.04/1000h（120天约 +17% / +12%），无突变。",
                "Wear 0.06/1000h (ball screw) and 0.04/1000h (cylinder), about +17% / +12% over 120 days; no step changes.",
            ),
            L(
                "前期 NORMAL，后期允许 WATCH；不得因正常老化升级为 WARNING；自适应基线不得吸收老化。",
                "NORMAL early, WATCH allowed late; normal aging must not escalate to WARNING; the adaptive baseline must not absorb aging.",
            ),
            [*NO_ABSTAIN, NO_RUL],
            [
                (
                    "BS1",
                    L("长期退化趋势可见", "Long-term degradation trend visible"),
                    [
                        E(0, 60, OK, "老化初期", "Early aging"),
                        E(60, 120, [H.NORMAL, H.WATCH], "老化后期可提示关注", "Late aging may be WATCH"),
                    ],
                ),
                (
                    "CY1",
                    L("伸出/缩回同步缓慢变化", "Extension and retraction drift slowly together"),
                    [
                        E(0, 60, OK, "老化初期", "Early aging"),
                        E(60, 120, [H.NORMAL, H.WATCH], "老化后期可提示关注", "Late aging may be WATCH"),
                    ],
                ),
            ],
            windows_per_day=2,
            aging=[
                {"target": "M01-BS1", "rate_per_1000h": 0.06},
                {"target": "M01-CY1", "rate_per_1000h": 0.04},
            ],
            limitations=[NO_WEAR_PROOF],
        )
    )
    S.append(
        Scenario(
            "S04",
            "torque_drift",
            L("异常转矩漂移", "Abnormal torque drift"),
            30,
            ["BS1", "LM1"],
            L(
                "第10–25天同工况下转矩残差持续上升；转速不变。",
                "Days 10–25: torque residual rises steadily under the same regimes; speed unchanged.",
            ),
            L(
                "丝杠摩擦参数线性增加 0.6（第10→25天）。",
                "Ball-screw friction parameter ramps +0.6 (day 10→25).",
            ),
            L(
                "10天前 NORMAL；漂移期 WATCH→WARNING；22天后 WARNING/CRITICAL。直线电机保持 NORMAL。",
                "NORMAL before day 10; WATCH→WARNING during the drift; WARNING/CRITICAL after day 22. Linear motor stays NORMAL.",
            ),
            [*NO_ABSTAIN, NO_RUL],
            [
                (
                    "BS1",
                    L("转矩残差漂移", "Torque residual drift"),
                    [
                        E(0, 10, OK, "漂移前", "Before drift"),
                        E(12, 22, NOT_NORMAL, "漂移中", "During drift"),
                        E(22, 30, DEGRADED, "漂移充分发展", "Drift fully developed"),
                    ],
                ),
                ("LM1", L("对照部件", "Control component"), [E(0, 30, OK, "无影响", "Unaffected")]),
            ],
            effects=[
                {
                    "target": "M01-BS1",
                    "parameter": "friction",
                    "shape": "LINEAR",
                    "start_h": 10 * D,
                    "end_h": 25 * D,
                    "magnitude": 0.6,
                }
            ],
            limitations=[NO_WEAR_PROOF],
        )
    )
    S.append(
        Scenario(
            "S05",
            "linear_motor_instability",
            L("直线电机速度不稳定", "Linear-motor speed instability"),
            14,
            ["LM1", "BS1"],
            L(
                "第7天起匀速段速度波动幅度明显增大。",
                "From day 7 the speed ripple during constant-speed segments grows markedly.",
            ),
            L("纹波参数阶跃 +0.04（约 0.5%→4.5%）。", "Ripple parameter step +0.04 (about 0.5% → 4.5%)."),
            L("7天前 NORMAL；8天后 WARNING/CRITICAL。", "NORMAL before day 7; WARNING/CRITICAL after day 8."),
            NO_ABSTAIN,
            [
                (
                    "LM1",
                    L("速度稳定性下降", "Speed stability degrades"),
                    [E(0, 7, OK, "正常", "Normal"), E(8, 14, DEGRADED, "波动增大", "Ripple increased")],
                ),
                ("BS1", L("对照部件", "Control component"), [E(0, 14, OK, "无影响", "Unaffected")]),
            ],
            effects=[
                {
                    "target": "M01-LM1",
                    "parameter": "ripple",
                    "shape": "STEP",
                    "start_h": 7 * D,
                    "magnitude": 0.04,
                }
            ],
        )
    )
    S.append(
        Scenario(
            "S06",
            "vacuum_release_increase",
            L("真空释放时间增加", "Vacuum-release duration increase"),
            30,
            ["VC1", "CY1"],
            L(
                "第10–25天释放时间由约80ms升至约120ms。",
                "Days 10–25: release time rises from about 80 ms to about 120 ms.",
            ),
            L("释放参数线性增加 0.5。", "Release parameter ramps +0.5."),
            L(
                "10天前 NORMAL；漂移期 WATCH/WARNING；之后 WARNING/CRITICAL。不得推断泄漏率。",
                "NORMAL before day 10; WATCH/WARNING during; WARNING/CRITICAL after. Leakage rate must not be inferred.",
            ),
            [
                L(
                    "泄漏率估计必须返回不支持（INELIGIBLE_INPUT）：仅有释放时间。",
                    "Leakage-rate estimation must return unsupported (INELIGIBLE_INPUT): only release time is available.",
                )
            ],
            [
                (
                    "VC1",
                    L("释放时间漂移", "Release-time drift"),
                    [
                        E(0, 10, OK, "漂移前", "Before drift"),
                        E(13, 22, NOT_NORMAL, "漂移中", "During drift"),
                        E(22, 30, DEGRADED, "漂移充分发展", "Drift fully developed"),
                    ],
                )
            ],
            effects=[
                {
                    "target": "M01-VC1",
                    "parameter": "release",
                    "shape": "LINEAR",
                    "start_h": 10 * D,
                    "end_h": 25 * D,
                    "magnitude": 0.5,
                }
            ],
            limitations=[
                L("释放时间不能单独推断泄漏率。", "Release duration alone cannot give a leakage rate.")
            ],
        )
    )
    for sid, slug, direction, other, zh_dir, noun in [
        ("S07", "cylinder_extend_slowdown", "extend", "retract", "伸出", "extension"),
        ("S08", "cylinder_retract_slowdown", "retract", "extend", "缩回", "retraction"),
    ]:
        S.append(
            Scenario(
                sid,
                slug,
                L(f"气缸{zh_dir}变慢", f"Cylinder {noun} slowdown"),
                21,
                ["CY1"],
                L(
                    f"第7–17天{zh_dir}时间上升约40%，另一方向不变。",
                    f"Days 7–17: {direction} time rises about 40%; the other direction is unchanged.",
                ),
                L(
                    f"{direction} 参数线性增加 0.4；{other} 不变。",
                    f"{direction} parameter ramps +0.4; {other} unchanged.",
                ),
                L(
                    "方向特定：受影响方向的证据升级到 WARNING，另一方向证据保持正常。",
                    "Direction-specific: evidence for the affected direction escalates to WARNING; the other direction stays normal.",
                ),
                NO_ABSTAIN,
                [
                    (
                        "CY1",
                        L(f"{zh_dir}方向异常", f"{direction.capitalize()} direction anomaly"),
                        [
                            E(0, 7, OK, "正常", "Normal"),
                            E(9, 15, NOT_NORMAL, "变慢中", "Slowing down"),
                            E(15, 21, DEGRADED, "明显变慢", "Clearly slower"),
                        ],
                    )
                ],
                effects=[
                    {
                        "target": "M01-CY1",
                        "parameter": direction,
                        "shape": "LINEAR",
                        "start_h": 7 * D,
                        "end_h": 17 * D,
                        "magnitude": 0.4,
                    }
                ],
            )
        )
    S.append(
        Scenario(
            "S09",
            "lubrication_improvement",
            L("润滑改善", "Lubrication improvement"),
            30,
            ["BS1"],
            L(
                "前14天润滑逐渐变差致转矩上升；第15天润滑后转矩回落，但累计老化不复位。",
                "Torque rises over 14 days as lubrication degrades; after lubrication on day 15 it drops, but accumulated aging is not reset.",
            ),
            L(
                "润滑参数 0→+0.25（0–14天）；第15天润滑 −0.25；老化 0.05/1000h 持续。",
                "Lubrication parameter 0→+0.25 (days 0–14); lubrication on day 15 applies −0.25; aging 0.05/1000h continues.",
            ),
            L(
                "润滑前 WATCH/WARNING；维护流程经稳定期和验证后回到 NORMAL_MONITORING；之后 NORMAL。",
                "WATCH/WARNING before lubrication; workflow passes stabilization and validation back to NORMAL_MONITORING; NORMAL afterwards.",
            ),
            [
                L(
                    "维护后稳定期内不做健康结论（UNKNOWN）。",
                    "No health conclusion during post-maintenance stabilization (UNKNOWN).",
                )
            ],
            [
                (
                    "BS1",
                    L("润滑后改善", "Improvement after lubrication"),
                    [
                        E(0, 6, OK, "润滑良好", "Well lubricated"),
                        E(10, 15, NOT_NORMAL, "润滑不足", "Under-lubricated"),
                        E(
                            15,
                            16,
                            [H.UNKNOWN],
                            "稳定期",
                            "Stabilization",
                            abstain=U.INSUFFICIENT_DATA,
                            workflow=POST_OK,
                        ),
                        E(17, 30, OK, "润滑后正常", "Normal after lubrication"),
                    ],
                )
            ],
            aging=[{"target": "M01-BS1", "rate_per_1000h": 0.05}],
            effects=[
                {
                    "target": "M01-BS1",
                    "parameter": "lubrication",
                    "shape": "LINEAR",
                    "start_h": 0,
                    "end_h": 14 * D,
                    "magnitude": 0.25,
                }
            ],
            maintenance=[
                {
                    "component_id": "M01-BS1",
                    "at_h": 15 * D,
                    "type": "LUBRICATION",
                    "parameter_deltas": {"lubrication": -0.25},
                }
            ],
        )
    )
    S.append(
        Scenario(
            "S10",
            "lubrication_deterioration",
            L("润滑后恶化", "Lubrication deterioration"),
            30,
            ["BS1"],
            L(
                "第15天润滑后转矩不降反升（如油脂错误或过量）。",
                "After lubrication on day 15 torque rises instead of falling (e.g., wrong grease or over-greasing).",
            ),
            L(
                "第15天润滑使润滑参数 +0.35。",
                "Lubrication on day 15 adds +0.35 to the lubrication parameter.",
            ),
            L(
                "维护前 NORMAL；维护后验证失败进入 REVIEW_REQUIRED；健康 WATCH/WARNING。",
                "NORMAL before; post-maintenance validation fails into REVIEW_REQUIRED; health WATCH/WARNING.",
            ),
            [
                L(
                    "维护后稳定期内不做健康结论（UNKNOWN）。",
                    "No health conclusion during post-maintenance stabilization (UNKNOWN).",
                )
            ],
            [
                (
                    "BS1",
                    L("润滑后恶化需复核", "Deterioration after lubrication needs review"),
                    [
                        E(0, 15, OK, "维护前正常", "Normal before maintenance"),
                        E(
                            15,
                            16,
                            [H.UNKNOWN],
                            "稳定期",
                            "Stabilization",
                            abstain=U.INSUFFICIENT_DATA,
                            workflow=POST_REVIEW,
                        ),
                        E(17, 30, [H.WATCH, H.WARNING], "维护后变差", "Worse after maintenance"),
                    ],
                )
            ],
            maintenance=[
                {
                    "component_id": "M01-BS1",
                    "at_h": 15 * D,
                    "type": "LUBRICATION",
                    "parameter_deltas": {"lubrication": 0.35},
                }
            ],
        )
    )
    S.append(
        Scenario(
            "S11",
            "partial_repair",
            L("部分维修", "Partial maintenance or repair"),
            40,
            ["CY1"],
            L(
                "伸出时间持续上升；第21天部分维修后下降但未回到初始水平。",
                "Extension time rises; after partial repair on day 21 it drops but not back to the initial level.",
            ),
            L(
                "伸出参数 0→+0.5（0–20天）；维修 −0.3，磨损 −0.02。",
                "Extend parameter 0→+0.5 (days 0–20); repair −0.3 and wear −0.02.",
            ),
            L(
                "维修前 WARNING；维修后 WATCH（部分改善）；影响分析报告部分恢复。",
                "WARNING before repair; WATCH after (partial improvement); impact analysis reports partial recovery.",
            ),
            [
                L(
                    "维护后稳定期内不做健康结论（UNKNOWN）。",
                    "No health conclusion during post-maintenance stabilization (UNKNOWN).",
                )
            ],
            [
                (
                    "CY1",
                    L("部分恢复", "Partial recovery"),
                    [
                        E(14, 21, DEGRADED, "维修前劣化", "Degraded before repair"),
                        E(
                            21,
                            22,
                            [H.UNKNOWN],
                            "稳定期",
                            "Stabilization",
                            abstain=U.INSUFFICIENT_DATA,
                            workflow=POST_REVIEW,
                        ),
                        E(23, 40, [H.WATCH], "部分恢复", "Partially recovered"),
                    ],
                )
            ],
            effects=[
                {
                    "target": "M01-CY1",
                    "parameter": "extend",
                    "shape": "LINEAR",
                    "start_h": 0,
                    "end_h": 20 * D,
                    "magnitude": 0.5,
                }
            ],
            maintenance=[
                {
                    "component_id": "M01-CY1",
                    "at_h": 21 * D,
                    "type": "PARTIAL_REPAIR",
                    "parameter_deltas": {"extend": -0.3},
                    "wear_delta": -0.02,
                }
            ],
        )
    )
    S.append(
        Scenario(
            "S12",
            "component_replacement",
            L("部件整体更换", "Complete component replacement"),
            40,
            ["BS1"],
            L(
                "摩擦持续上升；第21天更换后转矩回到新件水平，生命周期编号变化。",
                "Friction rises; after replacement on day 21 torque returns to new-part level and the lifecycle id changes.",
            ),
            L(
                "摩擦 0→+0.6（0–20天）；第21天更换生成 M01-BS1-LC2；历史保留。",
                "Friction 0→+0.6 (days 0–20); replacement on day 21 creates M01-BS1-LC2; history preserved.",
            ),
            L(
                "更换前 WARNING/CRITICAL；新生命周期初期无足够基线 → UNKNOWN；建立基线后 NORMAL。",
                "WARNING/CRITICAL before; UNKNOWN early in the new lifecycle without a baseline; NORMAL once a baseline exists.",
            ),
            [
                L(
                    "新生命周期在建立健康基线前必须弃权（INSUFFICIENT_DATA）。",
                    "The new lifecycle must abstain until a healthy baseline exists (INSUFFICIENT_DATA).",
                ),
                NO_RUL,
            ],
            [
                (
                    "BS1",
                    L("更换后新生命周期", "New lifecycle after replacement"),
                    [
                        E(14, 21, DEGRADED, "更换前劣化", "Degraded before replacement"),
                        E(
                            21,
                            24,
                            [H.UNKNOWN],
                            "新件无基线",
                            "New part without baseline",
                            abstain=U.INSUFFICIENT_DATA,
                            workflow=POST_OK,
                        ),
                        E(28, 40, OK, "新件正常", "New part normal"),
                    ],
                )
            ],
            aging=[{"target": "M01-BS1", "rate_per_1000h": 0.05}],
            effects=[
                {
                    "target": "M01-BS1",
                    "parameter": "friction",
                    "shape": "LINEAR",
                    "start_h": 0,
                    "end_h": 20 * D,
                    "magnitude": 0.6,
                }
            ],
            maintenance=[{"component_id": "M01-BS1", "at_h": 21 * D, "type": "REPLACEMENT"}],
        )
    )
    S.append(
        Scenario(
            "S13",
            "missing_duplicate",
            L("缺失与重复数据", "Missing and duplicated telemetry"),
            7,
            ["BS1", "CY1"],
            L(
                "第2–4天转矩约30%缺失；第3–6天伸出时间约20%重复。",
                "Days 2–4: about 30% of torque rows missing; days 3–6: about 20% of extension rows duplicated.",
            ),
            L("仅数据缺陷，设备健康。", "Data defects only; equipment healthy."),
            L(
                "报告缺失与重复；不得误报；数据不足处可 UNKNOWN。",
                "Report missing and duplicate data; no false alarms; UNKNOWN where data is insufficient.",
            ),
            [
                L(
                    "缺失过多的窗口应弃权（DATA_QUALITY）。",
                    "Windows with too many missing rows should abstain (DATA_QUALITY).",
                )
            ],
            [
                (
                    "BS1",
                    L("缺失数据", "Missing data"),
                    [
                        E(0, 2, OK, "正常", "Normal"),
                        E(2, 4, OK_OR_UNKNOWN, "缺失期间", "During missing data", flags=[Q.MISSING]),
                        E(4, 7, OK, "正常", "Normal"),
                    ],
                ),
                (
                    "CY1",
                    L("重复数据", "Duplicated data"),
                    [E(3, 6, OK_OR_UNKNOWN, "重复期间", "During duplicates", flags=[Q.DUPLICATE])],
                ),
            ],
            data_faults=[
                {
                    "kind": "MISSING",
                    "key_names": [key("BS1", "TRQ")],
                    "start_h": 2 * D,
                    "end_h": 4 * D,
                    "rate": 0.3,
                },
                {
                    "kind": "DUPLICATE",
                    "key_names": [key("CY1", "EXT")],
                    "start_h": 3 * D,
                    "end_h": 6 * D,
                    "rate": 0.2,
                },
            ],
        )
    )
    S.append(
        Scenario(
            "S14",
            "jitter_out_of_order",
            L("时间戳抖动与乱序", "Timestamp jitter and out-of-order records"),
            7,
            ["BS1", "LM1"],
            L(
                "第2–5天丝杠时间戳抖动约0.3s；直线电机约10%记录乱序。",
                "Days 2–5: ball-screw timestamps jitter about 0.3 s; about 10% of linear-motor rows arrive out of order.",
            ),
            L("仅时间戳缺陷，设备健康。", "Timestamp defects only; equipment healthy."),
            L(
                "报告抖动与乱序并排序后分析；不得误报。",
                "Report jitter and disorder, analyze after ordering; no false alarms.",
            ),
            NO_ABSTAIN,
            [
                (
                    "BS1",
                    L("时间戳抖动", "Timestamp jitter"),
                    [E(2, 5, OK_OR_UNKNOWN, "抖动期间", "During jitter", flags=[Q.JITTER])],
                ),
                (
                    "LM1",
                    L("记录乱序", "Out-of-order records"),
                    [E(2, 5, OK_OR_UNKNOWN, "乱序期间", "During disorder", flags=[Q.OUT_OF_ORDER])],
                ),
            ],
            data_faults=[
                {
                    "kind": "JITTER",
                    "key_names": [key("BS1", "SPD"), key("BS1", "TRQ")],
                    "start_h": 2 * D,
                    "end_h": 5 * D,
                    "jitter_s": 0.3,
                },
                {
                    "kind": "OUT_OF_ORDER",
                    "key_names": [key("LM1", "SPD")],
                    "start_h": 2 * D,
                    "end_h": 5 * D,
                    "rate": 0.1,
                },
            ],
        )
    )
    S.append(
        Scenario(
            "S15",
            "speed_torque_desync",
            L("速度/转矩不同步", "Speed/torque synchronization errors"),
            7,
            ["BS1"],
            L(
                "第2–5天转矩值滞后时间戳0.5s，转矩-速度关系变散。",
                "Days 2–5: torque values lag their timestamps by 0.5 s, smearing the torque–speed relationship.",
            ),
            L("同步偏移 0.5s；设备健康。", "Sync offset 0.5 s; equipment healthy."),
            L(
                "检测到未对齐（MISALIGNED）；转矩残差分析弃权；不得误报 WARNING。",
                "Misalignment detected (MISALIGNED); torque-residual analysis abstains; no false WARNING.",
            ),
            [
                L(
                    "对齐不可靠时转矩残差必须弃权（DATA_QUALITY）。",
                    "Torque residuals must abstain when alignment is unreliable (DATA_QUALITY).",
                )
            ],
            [
                (
                    "BS1",
                    L("速度/转矩未对齐", "Speed/torque misalignment"),
                    [
                        E(0, 2, OK, "正常", "Normal"),
                        E(
                            2,
                            5,
                            OK_OR_UNKNOWN,
                            "未对齐",
                            "Misaligned",
                            flags=[Q.MISALIGNED],
                            abstain=U.DATA_QUALITY,
                        ),
                        E(5, 7, OK, "恢复", "Recovered"),
                    ],
                )
            ],
            data_faults=[
                {
                    "kind": "SYNC_OFFSET",
                    "key_names": [key("BS1", "TRQ")],
                    "start_h": 2 * D,
                    "end_h": 5 * D,
                    "offset_s": 0.5,
                }
            ],
        )
    )
    S.append(
        Scenario(
            "S16",
            "bias_unit_mismatch",
            L("传感器偏置与单位错配", "Sensor bias and unit mismatch"),
            10,
            ["BS1", "VC1"],
            L(
                "第3–5天转矩偏置+5%额定（静止时也偏高）；第6–8天释放时间被放大1000倍（ms→µs）。",
                "Days 3–5: torque biased +5% rated (also high at standstill); days 6–8: release time scaled ×1000 (ms→µs).",
            ),
            L("仅传感/配置缺陷，设备健康。", "Sensor/configuration defects only; equipment healthy."),
            L(
                "单位异常标记 UNIT_SUSPECT/OUT_OF_RANGE 并弃权；偏置期间最多 WATCH（提示检查传感器），不得 WARNING。",
                "Flag UNIT_SUSPECT/OUT_OF_RANGE and abstain; at most WATCH during bias (check sensor), never WARNING.",
            ),
            [
                L(
                    "单位错配期间释放时间分析必须弃权（DATA_QUALITY）。",
                    "Release-time analysis must abstain during unit mismatch (DATA_QUALITY).",
                )
            ],
            [
                (
                    "BS1",
                    L("转矩偏置", "Torque bias"),
                    [
                        E(0, 3, OK, "正常", "Normal"),
                        E(3, 5, [H.NORMAL, H.WATCH, H.UNKNOWN], "偏置期间", "During bias"),
                        E(5.5, 10, OK, "恢复", "Recovered"),
                    ],
                ),
                (
                    "VC1",
                    L("单位错配", "Unit mismatch"),
                    [
                        E(
                            6,
                            8,
                            OK_OR_UNKNOWN,
                            "单位错配",
                            "Unit mismatch",
                            flags=[Q.UNIT_SUSPECT, Q.OUT_OF_RANGE],
                            abstain=U.DATA_QUALITY,
                        )
                    ],
                ),
            ],
            data_faults=[
                {
                    "kind": "BIAS",
                    "key_names": [key("BS1", "TRQ")],
                    "start_h": 3 * D,
                    "end_h": 5 * D,
                    "bias": 5.0,
                },
                {
                    "kind": "UNIT_SCALE",
                    "key_names": [key("VC1", "REL")],
                    "start_h": 6 * D,
                    "end_h": 8 * D,
                    "scale": 1000.0,
                },
            ],
        )
    )
    S.append(
        Scenario(
            "S17",
            "unknown_regime",
            L("未知/不支持工况", "Unknown or unsupported operating regime"),
            10,
            ["BS1", "CY1"],
            L(
                "第4–6天运行未登记配方 R-X（更高速度和负载）。",
                "Days 4–6: unregistered recipe R-X runs (higher speed and load).",
            ),
            L("工况超出已知集合；设备健康。", "Regime outside the known set; equipment healthy."),
            L(
                "R-X 期间返回不支持预测（UNSUPPORTED_REGIME）→ UNKNOWN；其余时间 NORMAL。",
                "During R-X return unsupported prediction (UNSUPPORTED_REGIME) → UNKNOWN; NORMAL otherwise.",
            ),
            [
                L(
                    "未知工况必须弃权（UNSUPPORTED_REGIME），不得用已知工况基线判定。",
                    "Unknown regimes must abstain (UNSUPPORTED_REGIME), never judged against known-regime baselines.",
                )
            ],
            [
                (
                    c,
                    L("未知工况弃权", "Abstain on unknown regime"),
                    [
                        E(0, 4, OK, "已知工况", "Known regime"),
                        E(4.1, 6, [H.UNKNOWN], "未知工况", "Unknown regime", abstain=U.UNSUPPORTED_REGIME),
                        E(6.1, 10, OK, "回到已知工况", "Back to known regime"),
                    ],
                )
                for c in ["BS1", "CY1"]
            ],
            recipe_schedule=[(4 * D, "R-X"), (6 * D, "R-A")],
        )
    )
    S.append(
        Scenario(
            "S18",
            "incomplete_operations",
            L("执行器动作未完成", "Incomplete actuator operations"),
            10,
            ["CY1", "VC1"],
            L(
                "第3–7天约5%气缸动作、约3%真空释放未完成，上报超时值2000ms。",
                "Days 3–7: about 5% of cylinder operations and 3% of vacuum releases do not complete; the timeout value 2000 ms is reported.",
            ),
            L(
                "未完成动作为注入事件；正常动作时间不变。",
                "Incomplete operations are injected events; completed durations are unchanged.",
            ),
            L(
                "未完成动作被识别并排除出时间统计；可 WATCH 提示动作失败；不得把超时值当作动作时间。",
                "Incomplete operations are detected and excluded from duration statistics; WATCH allowed for failed operations; timeout values are never treated as durations.",
            ),
            [
                L(
                    "超时值不得作为动作时间；窗口内有效动作不足时弃权（INSUFFICIENT_DATA）。",
                    "Timeout values are never used as durations; abstain when a window has too few completed operations (INSUFFICIENT_DATA).",
                )
            ],
            [
                (
                    c,
                    L("未完成动作", "Incomplete operations"),
                    [
                        E(0, 3, OK, "正常", "Normal"),
                        E(
                            3,
                            7,
                            [H.NORMAL, H.WATCH, H.UNKNOWN],
                            "存在未完成动作",
                            "Incomplete operations present",
                        ),
                        E(7.5, 10, OK, "恢复", "Recovered"),
                    ],
                )
                for c in ["CY1", "VC1"]
            ],
            incomplete_ops=[
                {"component_id": "M01-CY1", "start_h": 3 * D, "end_h": 7 * D, "rate": 0.05},
                {"component_id": "M01-VC1", "start_h": 3 * D, "end_h": 7 * D, "rate": 0.03},
            ],
            limitations=[
                L(
                    "用超时值表示未完成动作是待验证的假设。",
                    "Representing incomplete operations by the timeout value is an assumption to verify.",
                )
            ],
        )
    )
    S.append(
        Scenario(
            "S19",
            "shared_drive_chain",
            L("共用传动链异常", "Shared drive-chain abnormality"),
            21,
            ["BS1", "BS2", "LM1"],
            L(
                "第7–17天共用传动链的两根丝杠转矩同时上升。",
                "Days 7–17: torque of both ball screws on the shared drive chain rises simultaneously.",
            ),
            L("传动链 M01-DC1 摩擦 +0.5（线性）。", "Drive chain M01-DC1 friction +0.5 (linear)."),
            L(
                "两根丝杠均 WARNING；证据融合应提示共同原因（传动链），不应各自判定为丝杠磨损。",
                "Both ball screws WARNING; evidence fusion should indicate a common cause (drive chain) rather than separate ball-screw wear.",
            ),
            NO_ABSTAIN,
            [
                *[
                    (
                        c,
                        L("共用传动链", "Shared drive chain"),
                        [
                            E(0, 7, OK, "正常", "Normal"),
                            E(9, 15, NOT_NORMAL, "上升中", "Rising"),
                            E(15, 21, DEGRADED, "明显异常", "Clearly abnormal"),
                        ],
                    )
                    for c in ["BS1", "BS2"]
                ],
                ("LM1", L("对照部件", "Control component"), [E(0, 21, OK, "无影响", "Unaffected")]),
            ],
            effects=[
                {
                    "target": "M01-DC1",
                    "parameter": "friction",
                    "shape": "LINEAR",
                    "start_h": 7 * D,
                    "end_h": 17 * D,
                    "magnitude": 0.5,
                }
            ],
            limitations=[NO_WEAR_PROOF],
        )
    )
    S.append(
        Scenario(
            "S20",
            "source_interruption",
            L("数据源中断与恢复", "Data-source interruption and recovery"),
            10,
            ["BS1", "CY1"],
            L("第3–5天无任何数据，之后恢复。", "Days 3–5: no data at all, then recovery."),
            L("数据源中断48小时；设备健康。", "48-hour data-source interruption; equipment healthy."),
            L(
                "中断期间 UNKNOWN（INSUFFICIENT_DATA）；恢复后 NORMAL，恢复时不得误报；增量读取从水位线继续。",
                "UNKNOWN during the gap (INSUFFICIENT_DATA); NORMAL after recovery with no false alarm; incremental reads resume from the watermark.",
            ),
            [
                L(
                    "中断期间必须弃权（INSUFFICIENT_DATA）。",
                    "Must abstain during the interruption (INSUFFICIENT_DATA).",
                )
            ],
            [
                (
                    c,
                    L("中断与恢复", "Interruption and recovery"),
                    [
                        E(0, 3, OK, "正常", "Normal"),
                        E(
                            3,
                            5,
                            [H.UNKNOWN],
                            "中断",
                            "Interrupted",
                            flags=[Q.GAP],
                            abstain=U.INSUFFICIENT_DATA,
                        ),
                        E(5.2, 10, OK, "恢复", "Recovered"),
                    ],
                )
                for c in ["BS1", "CY1"]
            ],
            data_faults=[
                {
                    "kind": "INTERRUPTION",
                    "key_names": [key("BS1", "SPD"), key("BS1", "TRQ"), key("CY1", "EXT"), key("CY1", "RET")],
                    "start_h": 3 * D,
                    "end_h": 5 * D,
                }
            ],
        )
    )
    return S


# --- generation and verification ---------------------------------------------------------------


def _dump(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def build(data_dir: Path) -> dict[str, str]:
    """Write all scenarios, golden cases, fixtures, and checksums under data_dir. Returns checksums."""
    scen_dir = data_dir / "scenarios"
    scen_dir.mkdir(parents=True, exist_ok=True)
    cases: list[GoldenCase] = []
    for s in scenarios():
        out = scen_dir / f"{s.sid}_{s.slug}"
        meta = write_dataset(generate(s.config()), out, compress_csv=True)
        (out / "scenario.json").write_bytes(_dump(s.meta().model_dump(mode="json")))
        update_manifest(data_dir, meta, f"scenarios/{out.name}")
        cases.extend(s.golden_cases())
    (data_dir / "golden_cases").mkdir(exist_ok=True)
    (data_dir / "golden_cases" / "index.json").write_bytes(
        _dump(
            {
                "is_simulated": True,
                "notice": "Expectations for SIMULATED scenarios only; passing them is not evidence of real-world accuracy.",
                "cases": [c.model_dump(mode="json") for c in cases],
            }
        )
    )
    _fixtures(data_dir)
    write_fleet(data_dir)
    write_studio(data_dir)
    sums = {
        _logical(p).relative_to(data_dir).as_posix(): _content_sha(p)
        for sub in ("scenarios", "golden_cases", "fixtures")
        for p in sorted((data_dir / sub).rglob("*"))
        if p.is_file() and p.name not in ("checksums.json", "README.md")
    }
    (data_dir / "scenarios" / "checksums.json").write_bytes(_dump(sums))
    return sums


def _logical(p: Path) -> Path:
    return p.with_suffix("") if p.suffix == ".gz" else p


def _content_sha(p: Path) -> str:
    """Checksum of the uncompressed content, so results do not depend on the zlib build."""
    data = p.read_bytes()
    return hashlib.sha256(gzip.decompress(data) if p.suffix == ".gz" else data).hexdigest()


def _fixtures(data_dir: Path) -> None:
    """Small excerpts for fast unit tests (first rows of selected scenario files)."""
    fx = data_dir / "fixtures"
    fx.mkdir(exist_ok=True)
    picks = [
        ("S01_healthy", "normalized.csv", "M01-BS1.", 240, "S01_ball_screw_normalized.csv"),
        ("S14_jitter_out_of_order", "raw_telemetry.csv", "M01_LM1_SPD", 400, "S14_linear_motor_raw.csv"),
        ("S18_incomplete_operations", "raw_telemetry.csv", "M01_CY1_", 600, "S18_cylinder_raw.csv"),
    ]
    for scen, fname, prefix, n, target in picks:
        lines = read_text(data_dir / "scenarios" / scen / fname).splitlines()
        body = [ln for ln in lines[1:] if prefix in ln.split(",", 2)[0] + "," + ln.split(",", 2)[1]][:n]
        (fx / target).write_bytes(("\n".join([lines[0], *body]) + "\n").encode("utf-8"))


def verify(data_dir: Path) -> list[str]:
    """Regenerate into a temp dir and compare against stored checksums and committed files."""
    stored = json.loads((data_dir / "scenarios" / "checksums.json").read_text(encoding="utf-8"))
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        fresh = build(Path(tmp))
    if set(fresh) != set(stored):
        problems.append(f"file set differs: {sorted(set(fresh) ^ set(stored))}")
    for rel, digest in stored.items():
        if fresh.get(rel) != digest:
            problems.append(f"regenerated {rel} does not match stored checksum")
        path = data_dir / rel
        gz = path.with_name(path.name + ".gz")
        actual = _content_sha(path) if path.exists() else _content_sha(gz) if gz.exists() else None
        if actual != digest:
            problems.append(f"committed {rel} does not match stored checksum")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate or verify the 20 SIMULATED scenarios.")
    ap.add_argument("--data-dir", type=Path, default=DATA_DIR)
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    if a.verify:
        problems = verify(a.data_dir)
        for p in problems:
            print(f"ERROR: {p}")
        print("scenario verification:", "OK" if not problems else f"{len(problems)} problem(s)")
        sys.exit(1 if problems else 0)
    sums = build(a.data_dir)
    print(f"wrote {len(scenarios())} scenarios, {len(sums)} checksummed files")


if __name__ == "__main__":
    main()
