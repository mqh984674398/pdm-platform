"""maintenance impact analyses (T018)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "maintenance_impacts",
        sa.Column("workflow_id", sa.String(64), primary_key=True),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("result", sa.JSON, nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("maintenance_impacts")
