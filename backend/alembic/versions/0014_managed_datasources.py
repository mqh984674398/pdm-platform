"""data sources managed in the application (D-044)

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "managed_datasources",
        sa.Column("data_source_id", sa.String(64), primary_key=True),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column("layout", sa.JSON, nullable=False),
        sa.Column("scheme", sa.String(8), nullable=False),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("managed_datasources")
