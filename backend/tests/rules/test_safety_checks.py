"""D-043: the rule engine reports each safety check as violated, not evaluable or confirmed ok."""

from datetime import UTC, datetime, timedelta

from app.core.schemas import TimeWindow
from app.monitoring.rules.definitions import DEFAULT_RULES
from app.monitoring.rules.engine import evaluate
from app.monitoring.schemas import FeatureVector, SafetyStatus

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def vec(torque):
    return FeatureVector(
        component_id="BS1",
        lifecycle_id="BS1-LC1",
        regime_id=None,
        regime_status="KNOWN",
        catalog_id=None,
        feature_ref="ball_screw@1.1.0",
        window=TimeWindow(start=T0, end=T0 + timedelta(hours=1)),
        source_signals=[],
        values={"torque_p95": torque},
        is_simulated=True,
    )


def check(torque, limits):
    out = evaluate([vec(torque)], {}, DEFAULT_RULES, limits=limits)
    return out[0].safety_checks.get("SF-TORQUE-LIMIT")


def test_statuses():
    assert check(50.0, {"BS1": 100.0}) == SafetyStatus.CONFIRMED_OK
    assert check(120.0, {"BS1": 100.0}) == SafetyStatus.VIOLATED
    assert check(None, {"BS1": 100.0}) == SafetyStatus.NOT_EVALUATED  # invalid measurement
    assert check(50.0, {}) == SafetyStatus.NOT_CONFIGURED  # no limit set: not a measurement failure


def test_degraded_check_raises_a_watch_alarm_and_clears_when_measured(db):
    from app.core.security import Principal, Role
    from app.monitoring.alarms.service import AlarmService
    from app.monitoring.schemas import WindowEvaluation

    def win(i, status):
        w = TimeWindow(start=T0 + timedelta(hours=i), end=T0 + timedelta(hours=i + 1))
        return WindowEvaluation(
            component_id="BS1",
            lifecycle_id="BS1-LC1",
            window=w,
            feature_ref="ball_screw@1.1.0",
            level="NORMAL",
            evaluated=True,
            hits=[],
            statistics={},
            not_evaluated=["SF-TORQUE-LIMIT"] if status == SafetyStatus.NOT_EVALUATED else [],
            safety_checks={"SF-TORQUE-LIMIT": status},
            rules_version="r",
            is_simulated=True,
        )

    svc, who = AlarmService(db), Principal(user_id="system:test", role=Role.ENGINEER)
    raised, _ = svc.sync([win(0, SafetyStatus.NOT_EVALUATED)], who)
    (alarm,) = svc.alarms("BS1")
    assert len(raised) == 1 and alarm.rule_id == "DQ:SF-TORQUE-LIMIT" and alarm.severity.value == "WATCH"
    assert "不等于正常" in alarm.message.zh
    svc.sync([win(1, SafetyStatus.NOT_EVALUATED)], who)
    assert len(svc.alarms("BS1")) == 1  # not duplicated
    svc.sync([win(2, SafetyStatus.CONFIRMED_OK)], who)
    assert not svc.alarms("BS1")[0].condition_active  # measured again: the degraded condition clears
