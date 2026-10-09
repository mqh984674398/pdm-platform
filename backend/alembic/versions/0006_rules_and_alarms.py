"""rule settings, alarms and alarm watermarks (T017)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rule_settings",
        sa.Column("change_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("rule_set", sa.String(80), nullable=False),
        sa.Column("rule_id", sa.String(40), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("changed_by", sa.String(64), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("comment", sa.String(2000), nullable=False),
    )
    op.create_index("ix_rule_settings_rule_set", "rule_settings", ["rule_set"])
    op.create_table(
        "alarms",
        sa.Column("alarm_id", sa.String(40), primary_key=True),
        sa.Column("component_id", sa.String(64), nullable=False),
        sa.Column("lifecycle_id", sa.String(80), nullable=False),
        sa.Column("rule_id", sa.String(40), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(64), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(64), nullable=True),
        sa.Column("resolution_comment", sa.String(2000), nullable=False),
        sa.Column("condition_active", sa.Boolean, nullable=False),
        sa.Column("last_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message", sa.JSON, nullable=False),
        sa.Column("evidence_ids", sa.JSON, nullable=False),
        sa.Column("rules_version", sa.String(100), nullable=False),
        sa.Column("is_simulated", sa.Boolean, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
    )
    op.create_index("ix_alarms_component_id", "alarms", ["component_id"])
    op.create_index("ix_alarms_status", "alarms", ["status"])
    op.create_table(
        "alarm_watermarks",
        sa.Column("component_id", sa.String(64), primary_key=True),
        sa.Column("evaluated_until", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("alarm_watermarks")
    op.drop_table("alarms")
    op.drop_table("rule_settings")
