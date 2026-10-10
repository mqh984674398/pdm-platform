"""topology, component lifecycles, maintenance events and workflows (T014)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "machines",
        sa.Column("machine_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.JSON, nullable=False),
        sa.Column("line", sa.String(64), nullable=True),
        sa.Column("is_simulated", sa.Boolean, nullable=False),
    )
    op.create_table(
        "components",
        sa.Column("component_id", sa.String(64), primary_key=True),
        sa.Column("machine_id", sa.String(64), sa.ForeignKey("machines.machine_id"), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("name", sa.JSON, nullable=False),
        sa.Column("drive_chain_id", sa.String(64), nullable=True),
        sa.Column("signal_ids", sa.JSON, nullable=False),
    )
    op.create_index("ix_components_machine_id", "components", ["machine_id"])
    op.create_table(
        "component_lifecycles",
        sa.Column("lifecycle_id", sa.String(80), primary_key=True),
        sa.Column("component_id", sa.String(64), sa.ForeignKey("components.component_id"), nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("predecessor_lifecycle_id", sa.String(80), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("accumulated_operating_hours", sa.Float, nullable=False),
        sa.Column("accumulated_cycles", sa.Integer, nullable=False),
        sa.Column("usage_counted_until", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("component_id", "seq", name="uq_component_lifecycles_component_seq"),
    )
    op.create_index("ix_component_lifecycles_component_id", "component_lifecycles", ["component_id"])
    op.create_table(
        "maintenance_events",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("component_id", sa.String(64), nullable=False),
        sa.Column("lifecycle_id", sa.String(80), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("performed_by", sa.String(64), nullable=False),
        sa.Column("notes", sa.String(2000), nullable=False),
        sa.Column("new_lifecycle_id", sa.String(80), nullable=True),
        sa.Column("is_simulated", sa.Boolean, nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_maintenance_events_component_id", "maintenance_events", ["component_id"])
    op.create_index("ix_maintenance_events_lifecycle_id", "maintenance_events", ["lifecycle_id"])
    op.create_table(
        "maintenance_workflows",
        sa.Column("workflow_id", sa.String(64), primary_key=True),
        sa.Column("component_id", sa.String(64), nullable=False),
        sa.Column("lifecycle_id", sa.String(80), nullable=False),
        sa.Column("event_id", sa.String(64), nullable=False, unique=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_by", sa.String(64), nullable=True),
        sa.Column("transitions", sa.JSON, nullable=False),
        sa.Column("is_simulated", sa.Boolean, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
    )
    op.create_index("ix_maintenance_workflows_component_id", "maintenance_workflows", ["component_id"])


def downgrade() -> None:
    op.drop_table("maintenance_workflows")
    op.drop_table("maintenance_events")
    op.drop_table("component_lifecycles")
    op.drop_table("components")
    op.drop_table("machines")
