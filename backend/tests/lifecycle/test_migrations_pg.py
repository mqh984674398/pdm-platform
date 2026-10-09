"""T014 AC4: migrations apply and roll back cleanly on PostgreSQL (skipped without PDM_TEST_PG_URL)."""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.core.db import Base

from ..datasource.conftest import PG_URL

TABLES = {"machines", "components", "component_lifecycles", "maintenance_events", "maintenance_workflows"}


@pytest.mark.skipif(not PG_URL, reason="PDM_TEST_PG_URL not set")
def test_upgrade_downgrade_on_postgresql(monkeypatch):
    from app.core.config import get_settings

    engine = create_engine(PG_URL)
    Base.metadata.drop_all(engine)
    with engine.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS alembic_version"))
    monkeypatch.setenv("PDM_DATABASE_URL", PG_URL)
    get_settings.cache_clear()
    cfg = Config("alembic.ini")
    try:
        command.upgrade(cfg, "head")
        assert TABLES <= set(inspect(engine).get_table_names())
        command.downgrade(cfg, "0002")
        assert not TABLES & set(inspect(engine).get_table_names())
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        left = set(inspect(engine).get_table_names()) - {"alembic_version"}
        assert left == set(), left
    finally:
        get_settings.cache_clear()
        with engine.begin() as c:
            c.execute(text("DROP TABLE IF EXISTS alembic_version"))
        engine.dispose()
