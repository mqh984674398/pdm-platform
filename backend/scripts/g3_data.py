"""Golden Case comparison (T020 G3; fused levels added in T024) on the replayed SIMULATED demo fleet.

For every demo machine, the pipeline stores features, the demo engineer's verified references, alarms
and workflows in a scratch SQLite database. Each feature window's rule level is then compared with
the Golden Case expectation covering that window. Expectations that require abstention
(``must_abstain``) are counted separately: a rule level is not an abstention, so the dashboard's
UNKNOWN logic (no reference, validation running, stale data) is what covers them.

    python scripts/g3_data.py OUT.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
DATA = BACKEND.parent / "Data"
sys.path.insert(0, str(BACKEND))


def main(out: Path) -> None:
    import tempfile

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    import app.main  # noqa: F401  (registers tables)
    from app.core.db import Base
    from app.datasource.query_service.sources import DataSourceRegistry
    from app.decision.fleet import FleetHealthService
    from app.simulation.demo_pipeline import add_demo_source, demo_machines, run_pipeline

    golden = json.loads((DATA / "golden_cases" / "index.json").read_text(encoding="utf-8"))["cases"]
    machines = demo_machines(DATA)
    sources = DataSourceRegistry()
    add_demo_source(sources, machines)
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine(f"sqlite:///{tmp}/g3.db")
        Base.metadata.create_all(engine)
        with Session(engine) as s:
            results = {r.machine_id: r for r in run_pipeline(s, sources, machines)}
            svc = FleetHealthService(s)
            overview = svc.overview()
            cases = []
            for m in machines:
                for case in (c for c in golden if c["scenario_id"] == m.scenario_id):
                    cid = case["component_id"].replace("M01-", f"{m.machine_id}-")
                    evals, refs = svc._evaluate(cid)
                    fused = svc.window_decisions(cid)
                    spans = []
                    for exp in case["expectations"]:
                        span = [
                            e
                            for e in evals
                            if exp["start_h"] <= (e.window.start - m.t0).total_seconds() / 3600 < exp["end_h"]
                            and e.lifecycle_id in refs
                            and e.evaluated
                        ]
                        levels = [e.level.value for e in span]
                        ok = sum(lv in exp["allowed_health"] for lv in levels)
                        flv = [
                            r.decision.health_state.value
                            for r in fused
                            if exp["start_h"]
                            <= (r.decision.meta.data_window.start - m.t0).total_seconds() / 3600
                            < exp["end_h"]
                        ]
                        spans.append(
                            {
                                "start_h": exp["start_h"],
                                "end_h": exp["end_h"],
                                "allowed": exp["allowed_health"],
                                "must_abstain": exp.get("must_abstain"),
                                "windows": len(levels),
                                "within": ok,
                                "levels": {lv: levels.count(lv) for lv in sorted(set(levels))},
                                "fused_within": sum(lv in exp["allowed_health"] for lv in flv),
                                "fused_levels": {lv: flv.count(lv) for lv in sorted(set(flv))},
                                "note": exp.get("note"),
                            }
                        )
                    cases.append(
                        {
                            "case_id": case["case_id"],
                            "machine_id": m.machine_id,
                            "scenario_id": m.scenario_id,
                            "component_id": cid,
                            "spans": spans,
                        }
                    )
            report = {
                "is_simulated": True,
                "rules_version": overview.rules_version,
                "machines": [
                    {
                        "machine_id": r.machine_id,
                        "scenario_id": next(m.scenario_id for m in machines if m.machine_id == r.machine_id),
                        "windows": r.vectors,
                        "references": len(r.references),
                        "alarms_raised": r.alarms_raised,
                        "workflows": r.workflows,
                    }
                    for r in results.values()
                ],
                "current": [
                    {
                        "machine_id": fm.machine_id,
                        "component_id": c.component_id,
                        "health": c.health.value,
                        "reason": c.reason.model_dump(),
                        "open_alarms": c.open_alarms,
                    }
                    for fm in overview.machines
                    for c in fm.components
                ],
                "golden": cases,
            }
        engine.dispose()
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    graded = [s for c in cases for s in c["spans"] if not s["must_abstain"]]
    total, within = sum(s["windows"] for s in graded), sum(s["within"] for s in graded)
    fw = sum(s["fused_within"] for s in graded)
    print(
        f"wrote {out}: {len(cases)} cases, {within}/{total} graded windows within the allowed levels "
        f"(rules only), {fw}/{total} after evidence fusion"
    )
    for c in cases:
        for s in c["spans"]:
            if not s["must_abstain"] and s["windows"] and s["within"] < s["windows"]:
                print(
                    f"  {c['case_id']} {c['component_id']} {s['start_h']}-{s['end_h']} h: "
                    f"allowed {s['allowed']}, got {s['levels']}"
                )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
