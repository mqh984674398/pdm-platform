"""Per-check behaviour of the quality assessment on small synthetic series."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np

from app.core.schemas import TimeWindow
from app.monitoring.quality.assess import Rows, assess
from app.signals.schemas import QualityFlag as Q
from app.signals.schemas import SignalDefinition

T0 = datetime(2026, 2, 2, tzinfo=UTC).timestamp()
WINDOW = TimeWindow(
    start=datetime.fromtimestamp(T0, UTC), end=datetime.fromtimestamp(T0, UTC) + timedelta(days=1)
)


def sig(quantity="SPEED", unit="rpm", expected=2.0, **kw):
    return SignalDefinition(signal_id="s", name={"zh": "s", "en": "s"}, quantity=quantity, unit=unit,
                            expected_sampling_s=expected, **kw)  # fmt: skip


def windows(n_windows=4, per=60, step=2.0, spacing=6 * 3600, value=100.0):
    t = np.concatenate([T0 + 3 * 3600 + k * spacing + np.arange(per) * step for k in range(n_windows)])
    return t, np.full(t.size, value)


def rows(t, v, arrival=None):
    return Rows(t=np.asarray(t, float), v=np.asarray(v, float), arrival=arrival, is_simulated=True)


def test_clean_series_has_no_flags_and_reports_cadence():
    t, v = windows()
    rep = assess(sig(), rows(t, v, np.arange(t.size)), WINDOW)
    assert rep.flags == [] and rep.not_evaluated == [Q.UNIT_SUSPECT]
    assert rep.median_interval_s == 2.0 and rep.interval_jitter_s == 0.0
    assert rep.observation_window_count == 4 and rep.gap_count == 0 and rep.sample_count == 240


def test_missing_duplicates_and_null_values():
    t, v = windows()
    keep = np.ones(t.size, bool)
    keep[10:20] = False
    t2 = np.sort(np.concatenate([t[keep], t[[30, 31]]]))  # two duplicated rows
    v2 = np.full(t2.size, 100.0)
    v2[50] = np.nan
    rep = assess(sig(), rows(t2, v2), WINDOW)
    assert rep.duplicate_count == 2 and rep.missing_count == 10 + 1
    assert {Q.MISSING, Q.DUPLICATE} <= set(rep.flags)


def test_out_of_order_needs_storage_order():
    t, v = windows(1)
    arrival = np.arange(t.size)
    arrival[[5, 6]] = arrival[[6, 5]]  # stored swapped
    assert assess(sig(), rows(t, v, arrival), WINDOW).out_of_order_count == 1
    unknown = assess(sig(), rows(t, v, None), WINDOW)
    assert Q.OUT_OF_ORDER in unknown.not_evaluated and unknown.out_of_order_count == 0


def test_jitter_is_relative_to_expected_interval():
    t, v = windows(2)
    rng = np.random.default_rng(1)
    rep = assess(sig(), rows(np.sort(t + rng.normal(0, 0.3, t.size)), v), WINDOW)
    assert Q.JITTER in rep.flags and Q.MISSING not in rep.flags


def test_event_based_signals_skip_cadence_checks():
    t, v = windows(per=20, step=6.0)
    rep = assess(sig("DURATION", "s", None), rows(t, v * 0.001), WINDOW)
    assert {Q.MISSING, Q.JITTER} <= set(rep.not_evaluated) and rep.flags == []


def test_gap_threshold_follows_the_usual_pause():
    t, v = windows(4)
    t = np.concatenate([t[:120], t[180:]])  # drop the third observation window: 12 h pause
    assert Q.GAP not in assess(sig(), rows(t, v[: t.size]), WINDOW).flags
    t, v = windows(2)
    rep = assess(sig(), rows(t, v), WINDOW)  # nothing after hour ~9 of a 24 h window
    assert rep.gap_threshold_s == 24 * 3600 and Q.GAP not in rep.flags
    empty = assess(sig(), rows([], []), TimeWindow(start=WINDOW.start, end=WINDOW.start + timedelta(days=3)))
    assert Q.GAP in empty.flags and empty.sample_count == 0


def test_range_uses_signal_limits_before_unit_defaults():
    t, v = windows(1)
    v[3] = 25_000.0
    assert Q.OUT_OF_RANGE in assess(sig(), rows(t, v), WINDOW).flags  # rpm default +-20000
    own = assess(sig(valid_max=50.0), rows(t, v), WINDOW)
    assert own.valid_range == (None, 50.0) and own.out_of_range_count == t.size
    other = assess(sig("TORQUE", "N*m"), rows(t, v), WINDOW)
    assert Q.OUT_OF_RANGE in other.not_evaluated


def test_unit_scale_change_between_windows_and_against_reference():
    t, v = windows(4, per=20, step=6.0, value=0.08)
    v[40:] *= 1000  # windows 3-4 delivered in the wrong unit
    rep = assess(sig("DURATION", "s", None), rows(t, v), WINDOW)
    # the jump marks window 3; window 4 is consistent with 3 but still outside the plausible range
    assert rep.unit_suspect
    assert [s.flags for s in rep.spans] == [[Q.OUT_OF_RANGE, Q.UNIT_SUSPECT], [Q.OUT_OF_RANGE]]
    ref_t, ref_v = windows(4, per=20, step=6.0, value=0.08)
    scaled = assess(
        sig("DURATION", "s", None), rows(t[40:], v[40:]), WINDOW, reference=rows(ref_t - 86400, ref_v)
    )
    assert scaled.unit_suspect  # whole window scaled: only the reference reveals it


def test_a_pause_running_into_the_window_is_measured_from_the_last_row_before_it():
    t, v = windows(4)
    ref = rows(t - 2 * 86400, v)  # observation windows every 6 h, two days earlier
    late = t[t > T0 + 20 * 3600]  # this window only sees the last observation window, at ~21 h
    rep = assess(sig(), rows(late, np.full(late.size, 100.0)), WINDOW, reference=ref)
    (gap,) = [s for s in rep.spans if Q.GAP in s.flags]
    assert gap.start < WINDOW.start and rep.largest_gap_s > 40 * 3600
    # the same rows without the reference only see an 21 h lead-in, below the 24 h default
    assert Q.GAP not in assess(sig(), rows(late, np.full(late.size, 100.0)), WINDOW).flags
