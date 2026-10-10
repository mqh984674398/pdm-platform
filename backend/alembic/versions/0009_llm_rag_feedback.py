"""Ollama settings, RAG documents and chunks, user feedback (T027)

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_settings",
        sa.Column("version", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column("changed_by", sa.String(64), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "rag_documents",
        sa.Column("doc_id", sa.String(40), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("min_role", sa.String(16), nullable=False),
        sa.Column("source", sa.String(500), nullable=False),
        sa.Column("approved", sa.Boolean, nullable=False),
        sa.Column("added_by", sa.String(64), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by", sa.String(64), nullable=True),
    )
    op.create_table(
        "rag_chunks",
        sa.Column("chunk_id", sa.String(60), primary_key=True),
        sa.Column("doc_id", sa.String(40), nullable=False, index=True),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("embedding", sa.JSON, nullable=False),
        sa.Column("embed_model", sa.String(120), nullable=False),
    )
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("alarm_id", sa.String(80), nullable=True, index=True),
        sa.Column("decision_id", sa.String(120), nullable=True),
        sa.Column("maintenance_event_id", sa.String(80), nullable=True),
        sa.Column("assistant_ref", sa.String(200), nullable=True),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("comment", sa.String(2000), nullable=False),
        sa.Column("submitted_by", sa.String(64), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reviewed_by", sa.String(64), nullable=True),
        sa.Column("review_note", sa.String(2000), nullable=False),
    )


def downgrade() -> None:
    for t in ("feedback", "rag_chunks", "rag_documents", "llm_settings"):
        op.drop_table(t)
