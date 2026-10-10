"""No data-quality findings on scenarios without injected data faults (false-alarm guard)."""

from __future__ import annotations

import pytest

from .conftest import all_flags, scenario

CLEAN = ["S01", "S04", "S17", "S19"]  # healthy, torque drift, unknown regime, shared drive chain


@pytest.mark.parametrize("sid", CLEAN)
def test_no_flags_on_clean_scenario(sid):
    s = scenario(sid)
    ids = [x.signal_id for x in s.config.signals]
    start = 0.0
    while start < s.hours:
        end = min(start + 168, s.hours)
        assert all_flags(s.report(ids, start, end)) == set(), f"{sid} {start}-{end} h"
        start = end
