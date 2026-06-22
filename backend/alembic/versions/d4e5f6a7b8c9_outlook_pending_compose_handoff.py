"""Outlook add-in: pending compose handoff token on user (web → desktop compose)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("outlook_pending_compose_handoff_token", sa.Text(), nullable=True),
    )
    op.add_column(
        "user",
        sa.Column("outlook_pending_compose_handoff_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user", "outlook_pending_compose_handoff_expires_at")
    op.drop_column("user", "outlook_pending_compose_handoff_token")
