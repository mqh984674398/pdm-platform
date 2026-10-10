"""Signal API fixtures: the simulated Studio source "sim-iot" plus a SQLite IoTSharp-like source."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.core.audit  # noqa: F401  (registers tables)
import app.datasource.query_service.registry  # noqa: F401
import app.signals.registry  # noqa: F401
from app.core.db import Base, get_session
from app.datasource.query_service.sources import DataSourceRegistry
from app.datasource.sql import SqlAdapter
from app.main import create_app

from ..datasource.conftest import IOTSHARP_LIKE, PG_URL, seed_iotsharp_like, source_config
from ..query_service.conftest import Client

DATA = Path(__file__).resolve().parents[3] / "Data"
STUDIO_SOURCES = DATA / "fixtures" / "studio_sources.json"


@pytest.fixture(scope="session")
def sim_sources():
    return DataSourceRegistry.from_file(STUDIO_SOURCES)


@pytest.fixture(scope="session")
def sql_url(tmp_path_factory):
    url = f"sqlite:///{tmp_path_factory.mktemp('iot') / 'iot.db'}"
    seed_iotsharp_like(url, "S13")
    return url


@pytest.fixture
def sources(sim_sources, sql_url):
    reg = DataSourceRegistry()
    for cfg in sim_sources.configs():
        reg.add(cfg, sim_sources.adapter(cfg.data_source_id), sim_sources.datasets(cfg.data_source_id))
    cfg = source_config(data_source_id="iot", credential_ref="secret://pdm/iot-readonly", max_rows=1000)
    reg.add(cfg, SqlAdapter(cfg, IOTSHARP_LIKE, sql_url))
    return reg


@pytest.fixture
def client(sources, tmp_path):
    # The application database is PostgreSQL when a test server is configured (as in CI), else SQLite.
    engine = create_engine(PG_URL or f"sqlite:///{tmp_path / 'app.db'}")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    def session():
        with factory() as s:
            yield s

    application = create_app(sources=sources)
    application.dependency_overrides[get_session] = session
    yield Client(application)
    engine.dispose()


def signal(signal_id="M01-BS1.speed", unit="rpm", **kw):
    return {
        "signal_id": signal_id,
        "name": {"zh": signal_id, "en": signal_id},
        "quantity": "SPEED",
        "unit": unit,
        "expected_sampling_s": 2.0,
        **kw,
    }


def mapping(
    signal_id="M01-BS1.speed", key="M01_BS1_SPD", device="SIM-S13", source="sim-iot", unit="rpm", **kw
):
    return {
        "signal_id": signal_id,
        "data_source_id": source,
        "template_id": "telemetry-by-key-range",
        "device_id": device,
        "key_name": key,
        "time_field": "ts",
        "value_field": "value_double",
        "conversion": {"source_unit": unit, "target_unit": unit, "scale": 1.0, "offset": 0.0},
        **kw,
    }


def group(group_id="SIM-S13.G1", signal_ids=("M01-BS1.speed",)):
    return {"group_id": group_id, "name": {"zh": "组", "en": "Group"}, "signal_ids": list(signal_ids)}


def chart(template_id="viz-SIM-S13.G1", signal_ids=("M01-BS1.speed",), kind="LINE"):
    return {
        "template_id": template_id,
        "name": {"zh": "图", "en": "Chart"},
        "chart": kind,
        "signal_ids": list(signal_ids),
    }
