"""application settings, starting with the run mode (D-053)

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-15
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.String(200), nullable=False),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    # an installation that already registered a production source keeps showing it after the upgrade
    bind = op.get_bind()
    if "managed_datasources" in sa.inspect(bind).get_table_names():
        used = bind.execute(sa.text("SELECT COUNT(*) FROM managed_datasources")).scalar()
        if used:
            bind.execute(
                sa.text(
                    "INSERT INTO app_settings (key, value, updated_by, updated_at) "
                    "VALUES ('run_mode', 'production', 'system:migration', :now)"
                ),
                {"now": datetime.now(UTC)},
            )


def downgrade() -> None:
    op.drop_table("app_settings")
