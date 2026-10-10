"""One call for a machine and period: operating states, regimes, and movement cycles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from app.core.schemas import TimeWindow
from app.equipment.cycles import CycleSignal, infer_kind, motion_segments, operation_cycles
from app.equipment.regimes import assign_regimes
from app.equipment.schemas import MachineOperations, RegimeCatalog, RegimeStatus
from app.equipment.state import (
    NOT_DERIVED,
    Series,
    derive_states,
    is_operation,
    is_speed,
    observation_windows,
)


def analyze_machine(
    machine_id: str,
    series: Sequence[Series],
    window: TimeWindow,
    lifecycles: Mapping[str, str],
    catalog: RegimeCatalog | None = None,
    maintenance: Sequence[tuple[datetime, datetime, str]] = (),
    cycle_config: Mapping[str, CycleSignal] | None = None,
    include_motion_segments: bool = False,
) -> MachineOperations:
    """``lifecycles`` maps component id to its active lifecycle id for the period."""
    cycle_config = cycle_config or {}
    states = derive_states(series, window, maintenance)
    regimes = assign_regimes(series, window, catalog, cycle_config)
    cycles, summaries = [], []
    for s in series:
        cid = s.component_id
        if cid is None:
            continue
        lc = lifecycles.get(cid, f"{cid}-UNASSIGNED")
        if is_operation(s) and (s.signal.signal_id in cycle_config or infer_kind(s)):
            c, summary = operation_cycles(s, lc, window, cycle_config.get(s.signal.signal_id))
            cycles += c
            summaries.append(summary)
        elif include_motion_segments and is_speed(s):
            a, b = window.start.timestamp(), window.end.timestamp()
            cycles += motion_segments(s, lc, [w for w in observation_windows(series) if a <= w[0] < b])
    known = [r for r in regimes if r.status == RegimeStatus.KNOWN]
    for i, c in enumerate(cycles):
        r = next((r for r in known if r.start <= c.start <= r.end), None)
        if r is not None:
            cycles[i] = c.model_copy(update={"regime_id": r.regime_id})
    cycles.sort(key=lambda c: (c.start, c.cycle_id))
    return MachineOperations(
        machine_id=machine_id,
        window=window,
        states=states,
        regimes=regimes,
        cycles=cycles,
        cycle_summaries=summaries,
        catalog_id=catalog.catalog_id if catalog else None,
        not_evaluated=list(NOT_DERIVED),
        is_simulated=any(s.is_simulated for s in series),
    )
