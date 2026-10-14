"""prediction configuration versions (D-044)

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prediction_configs",
        sa.Column("config_id", sa.String(80), primary_key=True),
        sa.Column("component_id", sa.String(64), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("content", sa.JSON, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("validation", sa.JSON, nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_by", sa.String(64)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("publish_comment", sa.String(2000), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("prediction_configs")
