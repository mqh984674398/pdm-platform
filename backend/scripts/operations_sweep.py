"""T013 evidence: operating states, regimes, and actuator cycles for every simulated scenario.

Regimes are learned from each scenario's first 96 h (the reference period) and applied to the whole
scenario. Usage: python scripts/operations_sweep.py > ../contracts/evidence/T013/operations_sweep.log
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.equipment.operations import analyze_machine  # noqa: E402
from app.equipment.regimes import learn_catalog  # noqa: E402
from tests.equipment.conftest import DATA, scenario, series  # noqa: E402


def main() -> None:
    print("SIMULATED data only. Reference period for regimes: 0-96 h of each scenario.")
    for d in sorted((DATA / "scenarios").glob("S*_*")):
        sid = d.name.split("_")[0]
        sc, ser = scenario(sid), series(sid)
        cat = learn_catalog(ser, sc.machine, sc.window(0, min(96, sc.hours)), f"{sid}-ref")
        ops = analyze_machine(sc.machine, ser, sc.window(0, sc.hours), sc.lifecycles(), cat, sc.maintenance())
        states = Counter(s.state.value for s in ops.states if s.state.value != "UNKNOWN" or s.evidence)
        unknown_h = (
            sum((s.end - s.start).total_seconds() for s in ops.states if s.state.value == "UNKNOWN") / 3600
        )
        regimes = Counter(r.status.value for r in ops.regimes if r.state.value == "RUNNING")
        print(f"{d.name}")
        print(f"  states (observation windows/records): {dict(states)}; UNKNOWN {unknown_h:.1f} h")
        bands = [f"{r.regime.regime_id}[{r.regime.speed_band}] x{r.window_count}" for r in cat.regimes]
        print(f"  known regimes: {bands or 'none (no speed signal)'}")
        print(f"  running windows by regime status: {dict(regimes)}")
        for s in ops.cycle_summaries:
            med = f"{s.median_duration_s:.4f} s" if s.median_duration_s is not None else "-"
            timeout = (
                f"timeout {s.timeout_s:g} s{' (inferred)' if s.timeout_inferred else ''}"
                if s.timeout_s
                else ""
            )
            print(
                f"  {s.signal_id} {s.kind.value}: {s.operation_count} ops, {s.incomplete_count} incomplete, "
                f"{s.implausible_count} implausible, median completed {med} {timeout}".rstrip()
            )


if __name__ == "__main__":
    main()
