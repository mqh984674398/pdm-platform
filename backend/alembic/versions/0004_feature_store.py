"""feature schemas and feature vectors (T015)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feature_schemas",
        sa.Column("ref", sa.String(80), primary_key=True),
        sa.Column("component_type", sa.String(32), nullable=False),
        sa.Column("definition", sa.JSON, nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "feature_vectors",
        sa.Column("vector_id", sa.String(40), primary_key=True),
        sa.Column("component_id", sa.String(64), nullable=False),
        sa.Column("lifecycle_id", sa.String(80), nullable=False),
        sa.Column("regime_id", sa.String(32), nullable=True),
        sa.Column("regime_status", sa.String(16), nullable=False),
        sa.Column("catalog_id", sa.String(64), nullable=True),
        sa.Column("feature_ref", sa.String(80), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_signals", sa.JSON, nullable=False),
        sa.Column("values", sa.JSON, nullable=False),
        sa.Column("is_simulated", sa.Boolean, nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("component_id", "feature_ref", "window_start", name="uq_feature_vector"),
    )
    op.create_index("ix_feature_vectors_component_id", "feature_vectors", ["component_id"])
    op.create_index("ix_feature_vectors_lifecycle_id", "feature_vectors", ["lifecycle_id"])
    op.create_index("ix_feature_vectors_window_start", "feature_vectors", ["window_start"])


def downgrade() -> None:
    op.drop_table("feature_vectors")
    op.drop_table("feature_schemas")
