"""Statistics, persistence, hysteresis and determinism of the rule engine (L4-07)."""

from app.monitoring.rules.definitions import DEFAULT_RULES
from app.monitoring.rules.engine import evaluate
from app.monitoring.rules.statistics import cusum_upper, ewma, running_median
from app.monitoring.schemas import MonitoringLevel as L

from .conftest import after_reference, references


def test_statistics():
    assert running_median([1, 9, 2, 3], 3) == [None, None, 2.0, 3.0]
    assert cusum_upper([3, 3, 0, 10], 2) == [1.0, 2.0, 0.0, 4.0]  # clipped at 6
    assert ewma([10], 0.5) == [3.0]


def _shift(vectors, feature, start, values):
    out = list(vectors)
    for i, x in zip(range(start, start + len(values)), values, strict=True):
        out[i] = out[i].model_copy(update={"values": {**out[i].values, feature: x}})
    return out


def test_single_odd_window_raises_nothing_and_levels_hold(db):
    ref = references(db, "S01")["M01-BS1"]
    vs = after_reference("S01", "M01-BS1")
    st = ref.stats["torque_cruise_residual"]
    big = st.mean + 50 * st.std
    spike = evaluate(_shift(vs, "torque_cruise_residual", 5, [big]), {ref.lifecycle_id: ref}, DEFAULT_RULES)
    assert all(e.level == L.NORMAL for e in spike)
    run = evaluate(_shift(vs, "torque_cruise_residual", 5, [big] * 4), {ref.lifecycle_id: ref}, DEFAULT_RULES)
    levels = [e.level for e in run]
    assert levels[5] == L.NORMAL and levels[6] == L.CRITICAL  # median of 3 needs two of them
    assert levels[9:11] == [L.CRITICAL, L.CRITICAL]  # held after the run ends
    assert all(lv == L.NORMAL for lv in levels[13:])


def test_deterministic(db):
    ref = references(db, "S04")["M01-BS1"]
    vs = after_reference("S04", "M01-BS1")
    assert evaluate(vs, {ref.lifecycle_id: ref}, DEFAULT_RULES) == evaluate(
        vs, {ref.lifecycle_id: ref}, DEFAULT_RULES
    )


def test_without_reference_only_safety_rules_run():
    vs = after_reference("S04", "M01-BS1")
    evals = evaluate(vs, {}, DEFAULT_RULES)
    assert all(e.level == L.NORMAL and "ST-TORQUE" in e.not_evaluated for e in evals)
    assert not any(e.evaluated for e in evals)  # torque limit not configured either


def test_unsupported_regime_is_not_evaluated(db):
    from ..features.conftest import extraction

    ref = references(db, "S17")["M01-BS1"]
    vs = [v for v in extraction("S17").vectors if v.component_id == "M01-BS1"]
    unknown = {v.window.start for v in vs if v.regime_status == "UNSUPPORTED"}
    assert unknown
    evals = evaluate(vs, {ref.lifecycle_id: ref}, DEFAULT_RULES)
    for e in evals:
        if e.window.start in unknown:
            assert "ST-TORQUE" in e.not_evaluated and e.level == L.NORMAL
