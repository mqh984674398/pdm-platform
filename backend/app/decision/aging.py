"""Normal-aging grading (D-022): a slow, steady drift consistent with the component's age stays at WATCH.

The healthy reference stays frozen, so a component that ages normally drifts away from it slowly and
keeps drifting. A statistical rule hit is graded as aging when, over the current installation:

- the installation is at least ``min_age_days`` old (aging is a long-term effect),
- the robust (Theil-Sen) slope of the daily median deviation is at most ``max_rate_per_day`` over
  the whole installation and at most ``max_recent_rate_per_day`` over the last ``recent_days``
  (slow), and the recent slope is at most ``accel_ratio`` times the lifetime slope plus a noise
  allowance (not accelerating),
- the last ``step_days`` daily medians do not all lie more than ``max_step`` above the lifetime
  trend line (no abrupt change; a single noisy day is not a step),
- the current deviation is within what that rate allows for the component's age.

Safety rules are never graded as aging. Thresholds are in the rules' deviation units (robust z).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.stats import theilslopes

from app.core.schemas import LocalizedText


@dataclass(frozen=True)
class AgingPolicy:
    min_age_days: float = 30.0
    max_rate_per_day: float = 0.2
    recent_days: float = 21.0
    max_recent_rate_per_day: float = 0.35  # short windows are noisy
    accel_ratio: float = 2.0
    rate_noise: float = 0.1
    step_days: int = 3
    max_step: float = 2.5
    version: str = "aging-grading@1.0.0"


DEFAULT_POLICY = AgingPolicy()


@dataclass(frozen=True)
class AgingAssessment:
    is_aging: bool
    age_days: float
    lifetime_rate: float | None  # deviation per day
    recent_rate: float | None
    reason: LocalizedText


def _daily(points: Sequence[tuple[float, float]]) -> tuple[np.ndarray, np.ndarray]:
    days: dict[int, list[float]] = {}
    for h, v in points:
        days.setdefault(int(h // 24), []).append(v)
    d = np.array(sorted(days), dtype=float)
    return d, np.array([float(np.median(days[int(k)])) for k in d])


def _no(age: float, life: float | None, recent: float | None, zh: str, en: str) -> AgingAssessment:
    return AgingAssessment(False, age, life, recent, LocalizedText(zh=zh, en=en))


def assess(points: Sequence[tuple[float, float]], policy: AgingPolicy = DEFAULT_POLICY) -> AgingAssessment:
    """``points``: (hours since installation, persistent deviation) of one rule, oldest first, causal."""
    if not points:
        return _no(0.0, None, None, "没有偏差历史", "No deviation history")
    age = points[-1][0] / 24
    if age < policy.min_age_days:
        return _no(
            age,
            None,
            None,
            f"安装仅 {age:.0f} 天，不按老化处理",
            f"Installed only {age:.0f} days; not treated as aging",
        )
    d, v = _daily(points)
    if len(d) < 10:
        return _no(age, None, None, "可用天数不足，无法判断老化", "Too few days of data to judge aging")
    life, intercept, _, _ = theilslopes(v, d)
    recent_mask = d >= d[-1] - policy.recent_days
    recent = theilslopes(v[recent_mask], d[recent_mask])[0] if recent_mask.sum() >= 5 else life
    if life > policy.max_rate_per_day or recent > policy.max_recent_rate_per_day:
        rate = max(life, recent)
        return _no(
            age,
            life,
            recent,
            f"偏差每天增加 {rate:.2f}，快于正常老化",
            f"Deviation grows {rate:.2f}/day, faster than normal aging",
        )
    if recent > policy.accel_ratio * max(life, 0.0) + policy.rate_noise:
        return _no(
            age,
            life,
            recent,
            f"近期偏差加速（每天 {recent:.2f}，长期 {life:.2f}）",
            f"Drift is accelerating ({recent:.2f}/day recently vs {life:.2f}/day overall)",
        )
    resid = v[-policy.step_days :] - (intercept + life * d[-policy.step_days :])
    if float(resid.min()) > policy.max_step:
        return _no(
            age,
            life,
            recent,
            f"近期出现突变（持续高出趋势 {resid.min():.1f}）",
            f"Abrupt change recently (staying {resid.min():.1f} above the trend)",
        )
    if v[-1] > policy.max_rate_per_day * age + policy.max_step:
        return _no(
            age,
            life,
            recent,
            "偏差超出该寿命下正常老化的范围",
            "Deviation exceeds what normal aging allows at this age",
        )
    return AgingAssessment(
        True,
        age,
        life,
        recent,
        LocalizedText(
            zh=f"缓慢稳定漂移，符合正常老化（安装 {age:.0f} 天，每天 {life:.2f}），最高按“关注”处理",
            en=f"Slow, steady drift consistent with normal aging ({age:.0f} days installed, "
            f"{life:.2f}/day); graded WATCH at most",
        ),
    )
