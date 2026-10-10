"""champion/challenger deployment registry (T026)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deployment_versions",
        sa.Column("version_id", sa.String(96), primary_key=True),
        sa.Column("kind", sa.String(64), nullable=False, index=True),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("evaluation", sa.JSON, nullable=True),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.String(64), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comment", sa.String(2000), nullable=False),
        sa.Column("previous_version_id", sa.String(96), nullable=True),
        sa.Column("is_simulated", sa.Boolean, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("deployment_versions")
