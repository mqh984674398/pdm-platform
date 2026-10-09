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
