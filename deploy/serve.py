"""Production-mode server entry point for the Windows/LAN package (STK-05, T028).

Reads backend/.env (PDM_* settings), applies database migrations, loads the data sources in
PDM_DATASOURCES_FILE (non-simulated ones stay off unless PDM_PRODUCTION_DATA_APPROVED=true), and serves
the API and the built browser client on one port. With --simulated-fleet it also loads the labeled
SIMULATED demo fleet shipped in Data/ and, on an empty database, replays it once so the screens have
content for acceptance; every record it creates is marked simulated.

    cd backend
    .venv\\Scripts\\python.exe ..\\deploy\\serve.py --port 8080 [--simulated-fleet]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--simulated-fleet", action="store_true")
    args = ap.parse_args(argv)
    os.chdir(BACKEND)
    sys.path.insert(0, str(BACKEND))

    import uvicorn
    from alembic import command
    from alembic.config import Config
    from app.core.config import get_settings
    from app.core.db import get_engine
    from app.datasource.query_service.sources import DataSourceRegistry
    from app.main import create_app
    from app.monitoring.features.store import FeatureVectorRecord
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    settings = get_settings()
    if settings.auth_mode != "local":
        sys.exit(
            "Refusing to serve on the network with PDM_AUTH_MODE other than 'local'"
        )
    command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")
    path = settings.datasources_file
    sources = (
        DataSourceRegistry.from_file(
            Path(path), allow_production=settings.production_data_approved
        )
        if path
        else DataSourceRegistry()
    )
    if sources.skipped:
        print(
            f"Production data sources not enabled (needs G4 approval): {', '.join(sources.skipped)}"
        )
    if args.simulated_fleet:
        from app.simulation.demo_pipeline import (
            add_demo_source,
            demo_machines,
            run_pipeline,
        )

        fleet = demo_machines(ROOT / "Data")
        add_demo_source(sources, fleet)
        with Session(get_engine()) as session:
            if not session.scalar(
                select(func.count()).select_from(FeatureVectorRecord)
            ):
                for r in run_pipeline(session, sources, fleet):
                    print(
                        f"SIMULATED {r.machine_id}: {r.vectors} windows, {r.alarms_raised} alarms"
                    )
    from app.datasource.query_service.defaults import ensure_standard_templates

    with Session(get_engine()) as session:
        created = ensure_standard_templates(session, sources)
    if created:
        print(f"Registered built-in read-only query templates: {', '.join(created)}")
    uvicorn.run(
        create_app(sources=sources), host=args.host, port=args.port, log_level="info"
    )


if __name__ == "__main__":
    main()
