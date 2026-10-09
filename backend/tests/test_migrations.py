"""Alembic environment loads and runs against a throwaway database."""

from alembic import command
from alembic.config import Config


def test_alembic_upgrade_and_downgrade(tmp_path, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("PDM_DATABASE_URL", f"sqlite:///{tmp_path / 'm.db'}")
    get_settings.cache_clear()
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
    finally:
        get_settings.cache_clear()


def test_migrations_match_models(tmp_path, monkeypatch):
    """The migrated schema has every table and column the ORM models declare."""
    from sqlalchemy import create_engine, inspect

    import app.core.audit  # noqa: F401
    import app.datasource.query_service.registry  # noqa: F401
    import app.equipment.lifecycle  # noqa: F401
    import app.equipment.maintenance  # noqa: F401
    import app.monitoring.alarms.service  # noqa: F401
    import app.monitoring.baselines.verified  # noqa: F401
    import app.monitoring.features.store  # noqa: F401
    import app.monitoring.rules.settings  # noqa: F401
    import app.signals.registry  # noqa: F401
    from app.core.config import get_settings
    from app.core.db import Base

    url = f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setenv("PDM_DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        command.upgrade(Config("alembic.ini"), "head")
        insp = inspect(create_engine(url))
        for table in Base.metadata.sorted_tables:
            cols = {c["name"] for c in insp.get_columns(table.name)}
            assert cols == {c.name for c in table.columns}, table.name
    finally:
        get_settings.cache_clear()
