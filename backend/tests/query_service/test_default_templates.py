"""D-032: a fresh installation registers built-in read-only templates, once per source."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.main  # noqa: F401  (registers tables)
from app.core.db import Base
from app.core.security import Principal, Role
from app.datasource.query_service.defaults import ensure_standard_templates, standard_templates
from app.datasource.query_service.registry import TemplateRegistry
from app.datasource.query_service.sources import DataSourceRegistry
from app.datasource.query_service.sql_guard import check_template_sql
from app.datasource.schemas import DataSourceConfig, DataSourceKind
from app.datasource.simulated import SimulatedAdapter
from app.datasource.sql import SqlAdapter
from app.simulation.golden import scenario_dir
from app.simulation.studio_fixture import TEMPLATES

from ..datasource.conftest import IOTSHARP_LIKE, SIMULATOR_LIKE


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()


def _simulated(source_id="sim-iot") -> DataSourceRegistry:
    reg = DataSourceRegistry()
    cfg = DataSourceConfig(
        data_source_id=source_id, name="sim", kind=DataSourceKind.SIMULATED, read_only=True, is_simulated=True
    )
    reg.add(cfg, SimulatedAdapter(scenario_dir("S01"), source_id))
    return reg


def test_demo_source_gets_the_studio_templates(session):
    created = ensure_standard_templates(session, _simulated())
    assert created == ["telemetry-by-key-range", "telemetry-incremental"]
    active = {r.template_id: r for r in TemplateRegistry(session).list_active()}
    for template, sql in TEMPLATES:
        rec = active[template.template_id]
        assert rec.sql == sql and rec.created_by == "system:install"
        assert rec.to_template().parameters == template.parameters


def test_runs_once_and_respects_retirement(session):
    reg = _simulated()
    ensure_standard_templates(session, reg)
    TemplateRegistry(session).retire("telemetry-incremental", Principal(user_id="a", role=Role.ADMIN))
    session.commit()
    assert ensure_standard_templates(session, reg) == []
    assert [r.template_id for r in TemplateRegistry(session).list_active()] == ["telemetry-by-key-range"]


def test_other_sources_get_prefixed_ids(session):
    reg = _simulated("sim-demo-fleet")
    assert ensure_standard_templates(session, reg) == [
        "sim-demo-fleet-telemetry-by-key-range",
        "sim-demo-fleet-telemetry-incremental",
    ]


@pytest.mark.parametrize("layout", [IOTSHARP_LIKE, SIMULATOR_LIKE])
def test_sql_sources_use_their_layout(layout):
    adapter = SqlAdapter.__new__(SqlAdapter)  # layout only; no connection is opened
    adapter.layout = layout
    specs = standard_templates("plant-iot", adapter)
    table = f"{layout.schema_name}.{layout.table}" if layout.schema_name else layout.table
    for spec in specs:
        assert f"FROM {table}\n" in spec.sql
        assert f"{layout.time_column}" in spec.sql and layout.value_columns[0] in spec.sql
        assert spec.template_id.startswith("plant-iot-")
        check_template_sql(spec.sql, {p.name for p in spec.parameters}, {table.lower(), layout.table})
