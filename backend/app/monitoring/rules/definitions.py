"""The default rule set (versioned). Thresholds were set on simulated scenarios only.

Statistical rules use the deviation of a feature from the lifecycle's verified healthy reference
(per regime where the reference has it), in reference spreads, and fire on the median of the last
``persistence`` windows, so one odd window raises nothing. A sustained upward shift also raises WATCH
through the CUSUM. Safety rules check raw values against fixed limits, need no reference, and can
only be disabled by an administrator.
"""

from __future__ import annotations

from app.core.schemas import LocalizedText
from app.equipment.schemas import ComponentType as C
from app.monitoring.schemas import RuleDefinition, RuleKind, RuleSet

ST, SF = RuleKind.STATISTICAL, RuleKind.SAFETY


def _r(rid, kind, types, features, watch, warning, critical, zh, en) -> RuleDefinition:
    return RuleDefinition(
        rule_id=rid,
        kind=kind,
        component_types=[t.value for t in types],
        features=features,
        watch=watch,
        warning=warning,
        critical=critical,
        description=LocalizedText(zh=zh, en=en),
    )


DEFAULT_RULES = RuleSet(
    name="pdm-rules",
    version="1.0.0",
    persistence=3,
    hold=3,
    cusum_k=2.0,
    cusum_h=12.0,
    ewma_lambda=0.3,
    rules=[
        _r("ST-TORQUE", ST, [C.BALL_SCREW, C.LINEAR_MOTOR], ["torque_cruise_residual"], 4, 8, 25,
           "巡航扭矩残差偏离健康基准", "Cruise torque residual away from the healthy reference"),
        _r("ST-RIPPLE", ST, [C.LINEAR_MOTOR], ["speed_ripple"], 4, 8, 25,
           "速度波动偏离健康基准", "Speed ripple away from the healthy reference"),
        _r("ST-RELEASE", ST, [C.VACUUM_CUP], ["release_residual", "release_median"], 4, 8, 25,
           "破真空时间偏离健康基准", "Vacuum release time away from the healthy reference"),
        _r("ST-EXTEND", ST, [C.PNEUMATIC_CYLINDER], ["extend_residual", "extend_median"], 4, 8, 25,
           "气缸伸出时间偏离健康基准", "Cylinder extension time away from the healthy reference"),
        _r("ST-RETRACT", ST, [C.PNEUMATIC_CYLINDER], ["retract_residual", "retract_median"], 4, 8, 25,
           "气缸缩回时间偏离健康基准", "Cylinder retraction time away from the healthy reference"),
        _r("SF-INCOMPLETE", SF, [C.PNEUMATIC_CYLINDER, C.VACUUM_CUP],
           ["extend_incomplete_ratio", "retract_incomplete_ratio", "release_incomplete_ratio"],
           0.1, 0.5, None,
           "动作超时（未完成）比例过高", "Too many actuator operations timed out"),
        _r("SF-TORQUE-LIMIT", SF, [C.BALL_SCREW, C.LINEAR_MOTOR], ["torque_p95"], None, 0.9, 1.0,
           "扭矩接近或超过额定限值（相对限值）", "Torque near or above the configured limit"),
    ],
)  # fmt: skip
