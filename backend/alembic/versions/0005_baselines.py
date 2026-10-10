"""baselines: verified healthy references and stored snapshots (T016)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "baselines",
        sa.Column("baseline_id", sa.String(40), primary_key=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("component_id", sa.String(64), nullable=False),
        sa.Column("lifecycle_id", sa.String(80), nullable=False),
        sa.Column("regime_id", sa.String(32), nullable=True),
        sa.Column("feature_ref", sa.String(80), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stats", sa.JSON, nullable=False),
        sa.Column("regime_stats", sa.JSON, nullable=False),
        sa.Column("verified_by", sa.String(64), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comment", sa.String(2000), nullable=False),
        sa.Column("superseded_by", sa.String(40), nullable=True),
        sa.Column("meta", sa.JSON, nullable=False),
    )
    op.create_index("ix_baselines_component_id", "baselines", ["component_id"])
    op.create_index("ix_baselines_lifecycle_id", "baselines", ["lifecycle_id"])


def downgrade() -> None:
    op.drop_table("baselines")
