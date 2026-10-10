"""signal configuration versions (T011)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signal_config_versions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("version", sa.Integer, nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("comment", sa.String(500), nullable=False),
        sa.Column("content_hash", sa.String(71), nullable=False),
        sa.Column("content", sa.JSON, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("signal_config_versions")
