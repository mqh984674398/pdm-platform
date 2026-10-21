"""machine order and background picture on the equipment overview (D-054)

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "machine_layout",
        sa.Column("machine_id", sa.String(64), primary_key=True),
        sa.Column("sort", sa.Integer, nullable=True),
        sa.Column("background", sa.Text, nullable=True),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("machine_layout")
