"""component torque limit (D-041) and healthy-reference quality warnings (D-040)

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("components") as batch:
        batch.add_column(sa.Column("torque_limit", sa.Float, nullable=True))
    with op.batch_alter_table("baselines") as batch:
        batch.add_column(sa.Column("warnings", sa.JSON, nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("components") as batch:
        batch.drop_column("torque_limit")
    with op.batch_alter_table("baselines") as batch:
        batch.drop_column("warnings")
