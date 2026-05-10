"""Outlook send capture: pending matter context on user; conversation id on file."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "n7o8p9q0r1"
down_revision = "m5n6o7p8q9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("file", sa.Column("source_outlook_conversation_id", sa.Text(), nullable=True))
    op.create_index(
        "ix_file_source_outlook_conversation_id",
        "file",
        ["source_outlook_conversation_id"],
    )

    op.add_column(
        "user",
        sa.Column(
            "outlook_pending_send_case_id",
            UUID(as_uuid=True),
            sa.ForeignKey("case.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "user",
        sa.Column(
            "outlook_pending_send_source_file_id",
            UUID(as_uuid=True),
            sa.ForeignKey("file.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "user",
        sa.Column("outlook_pending_send_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user", "outlook_pending_send_expires_at")
    op.drop_column("user", "outlook_pending_send_source_file_id")
    op.drop_column("user", "outlook_pending_send_case_id")
    op.drop_index("ix_file_source_outlook_conversation_id", table_name="file")
    op.drop_column("file", "source_outlook_conversation_id")
