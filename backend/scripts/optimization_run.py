"""Replay the SIMULATED demo fleet and write a champion/challenger run (T025 evidence).

python scripts/optimization_run.py OUT.json [--candidates 12] [--seed 0]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
DATA = BACKEND.parent / "Data"
sys.path.insert(0, str(BACKEND))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--candidates", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    import app.main  # noqa: F401
    from app.core.db import Base
    from app.core.security import Principal, Role
    from app.datasource.query_service.sources import DataSourceRegistry
    from app.optimization.service import OptimizationService
    from app.optimization.suite import demo_suite
    from app.simulation.demo_pipeline import add_demo_source, demo_machines, run_pipeline

    machines = demo_machines(DATA)
    sources = DataSourceRegistry()
    add_demo_source(sources, machines)
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine(f"sqlite:///{tmp}/opt.db")
        Base.metadata.create_all(engine)
        with Session(engine) as s:
            run_pipeline(s, sources, machines)
            svc = OptimizationService(s, demo_suite(s, DATA))
            run = svc.run(
                Principal(user_id="evidence-script", role=Role.ENGINEER), args.candidates, args.seed
            )
        engine.dispose()
    args.out.write_text(run.model_dump_json(indent=1) + "\n", encoding="utf-8")
    c = run.champion.metrics
    print(f"champion {c.within}/{c.windows} (over {c.over}, under {c.under}); recommended {run.recommended}")
    for r in sorted(run.candidates, key=lambda r: -r.metrics.within):
        m = r.metrics
        print(f"  {r.candidate_id} {r.changes} {m.within}/{m.windows} over {m.over} under {m.under}")


if __name__ == "__main__":
    main()
