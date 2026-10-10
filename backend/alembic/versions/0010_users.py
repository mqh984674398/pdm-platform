"""local user accounts (T028)

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("failed", sa.Integer, nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("users")
