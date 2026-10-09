"""Run the API against the simulated Studio source with a fresh demo database (T011).

Used by the frontend end-to-end tests and for local demos. It never touches a configured production
database: the database is a new SQLite file, recreated on every start.

    python scripts/demo_server.py --db /tmp/pdm-demo.db --port 8765
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
DATA = BACKEND.parent / "Data"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True, help="SQLite file to (re)create")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()

    db = args.db.resolve()
    db.parent.mkdir(parents=True, exist_ok=True)
    db.unlink(missing_ok=True)
    os.environ["PDM_DATABASE_URL"] = f"sqlite:///{db}"
    os.environ["PDM_DATASOURCES_FILE"] = str(DATA / "fixtures" / "studio_sources.json")
    os.environ.setdefault("PDM_AUTH_MODE", "dev")
    sys.path.insert(0, str(BACKEND))
    os.chdir(BACKEND)

    import uvicorn
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.orm import Session

    from app.core.db import get_engine
    from app.core.security import Principal, Role
    from app.datasource.query_service.registry import TemplateRegistry
    from app.datasource.query_service.service import allowed_tables
    from app.datasource.query_service.sources import DataSourceRegistry
    from app.datasource.schemas import QueryTemplateSpec
    from app.simulation.studio_fixture import TEMPLATES

    command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")
    sources = DataSourceRegistry.from_file(Path(os.environ["PDM_DATASOURCES_FILE"]))
    seed = Principal(user_id="demo-seed", role=Role.ADMIN)
    with Session(get_engine()) as session:
        registry = TemplateRegistry(session)
        for template, sql in TEMPLATES:
            fields = template.model_dump(exclude={"version"})
            spec = QueryTemplateSpec(**fields, sql=sql)
            registry.create(spec, seed, allowed_tables(sources.adapter(spec.data_source_id)))
        session.commit()

    from app.main import create_app

    uvicorn.run(create_app(sources=sources), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
