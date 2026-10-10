"""per-role module visibility (D-033)

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "role_modules",
        sa.Column("role", sa.String(16), primary_key=True),
        sa.Column("modules", sa.JSON, nullable=False),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("role_modules")
