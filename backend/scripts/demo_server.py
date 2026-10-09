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
    from app.datasource.schemas import DataSourceConfig, DataSourceKind, QueryTemplateSpec
    from app.datasource.simulated import SimulatedAdapter
    from app.signals.registry import SignalConfigStore
    from app.signals.schemas import DeviceConfigChange
    from app.simulation.bench import DEVICE, KEY, write_bench_dataset
    from app.simulation.studio_fixture import TEMPLATES

    command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")
    sources = DataSourceRegistry.from_file(Path(os.environ["PDM_DATASOURCES_FILE"]))
    # T019: a dense SIMULATED signal (>= 1M points) for chart performance checks
    bench_dir = db.parent / "bench"
    if not (bench_dir / "raw_telemetry.csv.gz").exists():
        write_bench_dataset(bench_dir)
    bench = DataSourceConfig(
        data_source_id="sim-bench",
        name="SIM chart bench",
        kind=DataSourceKind.SIMULATED,
        read_only=True,
        is_simulated=True,
        max_rows=2_000_000,
    )
    sources.add(bench, SimulatedAdapter(bench_dir, "sim-bench"))
    seed = Principal(user_id="demo-seed", role=Role.ADMIN)
    with Session(get_engine()) as session:
        registry = TemplateRegistry(session)
        for template, sql in TEMPLATES:
            fields = template.model_dump(exclude={"version"})
            spec = QueryTemplateSpec(**fields, sql=sql)
            registry.create(spec, seed, allowed_tables(sources.adapter(spec.data_source_id)))
        SignalConfigStore(session).replace_device(
            "sim-bench",
            DEVICE,
            DeviceConfigChange.model_validate(
                {
                    "comment": "SIMULATED chart bench signal",
                    "signals": [
                        {
                            "signal_id": "BENCH.torque",
                            "name": {"zh": "基准测试扭矩（模拟）", "en": "Bench torque (simulated)"},
                            "quantity": "TORQUE",
                            "unit": "Nm",
                            "expected_sampling_s": 1.0,
                        }
                    ],
                    "mappings": [
                        {
                            "signal_id": "BENCH.torque",
                            "data_source_id": "sim-bench",
                            "template_id": "bench",
                            "device_id": DEVICE,
                            "key_name": KEY,
                            "time_field": "ts",
                            "value_field": "value_double",
                        }
                    ],
                }
            ),
            seed,
        )
        session.commit()

    from app.main import create_app

    uvicorn.run(create_app(sources=sources), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
