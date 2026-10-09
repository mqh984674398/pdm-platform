"""Declared feature sets per component type (L4-04).

A feature set version is immutable once published: the store refuses a changed definition under an
existing ``feature_set@version``. Cam and gear have no telemetry and therefore no feature set.
"""

from __future__ import annotations

from app.core.schemas import LocalizedText
from app.equipment.schemas import ComponentType
from app.monitoring.schemas import FeatureDef, FeatureSchema


def _f(name: str, unit: str, zh: str, en: str, residual: bool = False) -> FeatureDef:
    return FeatureDef(name=name, unit=unit, description=LocalizedText(zh=zh, en=en), residual=residual)


def _axis(feature_set: str, ctype: ComponentType) -> FeatureSchema:
    # 1.1.0 (T017) adds speed_ripple; 1.0.0 vectors stay valid under their own registered schema
    return FeatureSchema(
        feature_set=feature_set,
        version="1.1.0",
        component_type=ctype.value,
        features=[
            _f("speed_cruise", "rpm", "巡航速度中位数", "Median speed in the cruise phase"),
            _f("speed_rms", "rpm", "速度均方根", "RMS speed while moving"),
            _f(
                "speed_ripple",
                "ratio",
                "巡航速度波动（稳健离散度/巡航速度）",
                "Speed ripple in the cruise phase (robust spread / cruise level)",
            ),
            _f("torque_cruise", "Nm", "巡航阶段扭矩中位数", "Median absolute torque in the cruise phase"),
            _f("torque_rms", "Nm", "扭矩均方根", "RMS torque"),
            _f("torque_p95", "Nm", "扭矩95分位", "95th percentile absolute torque"),
            _f(
                "torque_cruise_residual",
                "robust_z",
                "工况归一化巡航扭矩残差",
                "Cruise torque residual against the matched regime",
                residual=True,
            ),
        ],
    )


def _actuator(feature_set: str, ctype: ComponentType, ops: list[tuple[str, str, str]]) -> FeatureSchema:
    feats = [_f("operation_count", "count", "动作次数", "Operations in the window")]
    for op, zh, en in ops:
        feats += [
            _f(f"{op}_median", "s", f"{zh}时间中位数", f"Median {en} duration (completed operations)"),
            _f(f"{op}_p90", "s", f"{zh}时间90分位", f"90th percentile {en} duration"),
            _f(
                f"{op}_incomplete_ratio",
                "ratio",
                f"{zh}未完成比例",
                f"Share of {en} operations that timed out",
            ),
            _f(
                f"{op}_residual",
                "robust_z",
                f"工况归一化{zh}时间残差",
                f"{en.capitalize()} duration residual against the matched regime",
                residual=True,
            ),
        ]
    return FeatureSchema(feature_set=feature_set, version="1.0.0", component_type=ctype.value, features=feats)


FEATURE_SETS: dict[ComponentType, FeatureSchema] = {
    ComponentType.BALL_SCREW: _axis("ball_screw", ComponentType.BALL_SCREW),
    ComponentType.LINEAR_MOTOR: _axis("linear_motor", ComponentType.LINEAR_MOTOR),
    ComponentType.PNEUMATIC_CYLINDER: _actuator(
        "pneumatic_cylinder",
        ComponentType.PNEUMATIC_CYLINDER,
        [("extend", "伸出", "extension"), ("retract", "缩回", "retraction")],
    ),
    ComponentType.VACUUM_CUP: _actuator(
        "vacuum_cup", ComponentType.VACUUM_CUP, [("release", "破真空", "vacuum release")]
    ),
}

MIN_OPERATIONS = 3  # completed operations needed for a duration median in one window
