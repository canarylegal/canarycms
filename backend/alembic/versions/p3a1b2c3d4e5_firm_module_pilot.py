"""Firm module case state + lifecycle outbox (Phase 3 pilot).

Revision ID: p3a1b2c3d4e5
Revises: p2a1b2c3d4e5
Create Date: 2026-10-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "p3a1b2c3d4e5"
down_revision = "p2a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "firm_module_case_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("module_id", sa.String(length=80), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("case.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("module_id", "case_id", name="uq_firm_module_case_state_module_case"),
    )
    op.create_index("ix_firm_module_case_state_case_id", "firm_module_case_state", ["case_id"])

    op.create_table(
        "firm_lifecycle_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_firm_lifecycle_outbox_processed_at", "firm_lifecycle_outbox", ["processed_at"])


def downgrade() -> None:
    op.drop_index("ix_firm_lifecycle_outbox_processed_at", table_name="firm_lifecycle_outbox")
    op.drop_table("firm_lifecycle_outbox")
    op.drop_index("ix_firm_module_case_state_case_id", table_name="firm_module_case_state")
    op.drop_table("firm_module_case_state")
