"""Run the quality and alignment checks over every simulated scenario in 48 h windows and print which
flags appear where (T012 evidence). Expected: flags only on the scenarios with injected data faults.

    python scripts/quality_sweep.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.core.schemas import TimeWindow  # noqa: E402
from app.datasource.query_service.sources import DataSourceRegistry  # noqa: E402
from app.datasource.schemas import DataSourceConfig, DataSourceKind  # noqa: E402
from app.datasource.simulated import SimulatedAdapter  # noqa: E402
from app.monitoring.quality.service import quality_report  # noqa: E402
from app.monitoring.schemas import QualityRequest  # noqa: E402
from app.signals.schemas import SignalConfig  # noqa: E402

STEP_H = 48


def main() -> None:
    for d in sorted((BACKEND.parent / "Data" / "scenarios").glob("S*_*")):
        topo = json.loads((d / "topology.json").read_text(encoding="utf-8"))
        cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
        t0 = datetime.fromisoformat(cfg["start"].replace("Z", "+00:00"))
        reg = DataSourceRegistry()
        source = DataSourceConfig(data_source_id="simulated", name=d.name, kind=DataSourceKind.SIMULATED,
                                  read_only=True, is_simulated=True)  # fmt: skip
        reg.add(source, SimulatedAdapter(d))
        config = SignalConfig(signals=topo["signals"], mappings=topo["mappings"])
        ids = [s.signal_id for s in config.signals]
        hits: dict[str, list[str]] = {}
        h = 0.0
        while h < cfg["duration_hours"]:
            end = min(h + STEP_H, cfg["duration_hours"])
            w = TimeWindow(start=t0 + timedelta(hours=h), end=t0 + timedelta(hours=end))
            resp = quality_report(reg, config, QualityRequest(signal_ids=ids, window=w))
            for r in resp.reports:
                for f in r.flags:
                    hits.setdefault(f"{r.signal_id} {f.value}", []).append(f"{h:g}-{end:g}h")
            for a in resp.alignment:
                for f in a.flags:
                    hits.setdefault(f"{a.speed_signal_id}+{a.torque_signal_id} {f.value}", []).append(
                        f"{h:g}-{end:g}h"
                    )
            h = end
        print(d.name)
        for k, v in sorted(hits.items()):
            print(f"  {k}: {', '.join(v)}")
        if not hits:
            print("  (no flags)")


if __name__ == "__main__":
    main()
