"""audit log and query template registry (T010)

Revision ID: 0001
Revises:
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("actor_role", sa.String(16), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("object_type", sa.String(32), nullable=False),
        sa.Column("object_id", sa.String(128), nullable=False),
        sa.Column("details", sa.JSON, nullable=False),
    )
    op.create_index("ix_audit_log_object_type", "audit_log", ["object_type"])
    op.create_index("ix_audit_log_object_id", "audit_log", ["object_id"])
    op.create_table(
        "query_templates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("template_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("data_source_id", sa.String(64), nullable=False),
        sa.Column("spec", sa.JSON, nullable=False),
        sa.Column("sql", sa.Text, nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("template_id", "version"),
    )
    op.create_index("ix_query_templates_template_id", "query_templates", ["template_id"])


def downgrade() -> None:
    op.drop_index("ix_query_templates_template_id", "query_templates")
    op.drop_table("query_templates")
    op.drop_index("ix_audit_log_object_id", "audit_log")
    op.drop_index("ix_audit_log_object_type", "audit_log")
    op.drop_table("audit_log")
