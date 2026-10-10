"""plant structure: workshops, processes, machine placement and device binding (D-037)

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plant_nodes",
        sa.Column("node_id", sa.String(64), primary_key=True),
        sa.Column("parent_id", sa.String(64), sa.ForeignKey("plant_nodes.node_id"), nullable=True),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("name", sa.JSON, nullable=False),
        sa.Column("sort", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_plant_nodes_parent_id", "plant_nodes", ["parent_id"])
    with op.batch_alter_table("machines") as batch:
        batch.add_column(sa.Column("process_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("device_id", sa.String(128), nullable=True))
        batch.create_index("ix_machines_process_id", ["process_id"])
        batch.create_index("ix_machines_device_id", ["device_id"])


def downgrade() -> None:
    with op.batch_alter_table("machines") as batch:
        batch.drop_index("ix_machines_device_id")
        batch.drop_index("ix_machines_process_id")
        batch.drop_column("device_id")
        batch.drop_column("process_id")
    op.drop_index("ix_plant_nodes_parent_id", table_name="plant_nodes")
    op.drop_table("plant_nodes")
