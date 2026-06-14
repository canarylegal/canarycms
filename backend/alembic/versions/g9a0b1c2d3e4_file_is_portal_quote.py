"""Add is_portal_quote on file for portal accept/decline workflow."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "g9a0b1c2d3e4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "file",
        sa.Column("is_portal_quote", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.execute(
        sa.text(
            """
            UPDATE file
            SET is_portal_quote = true
            WHERE id IN (SELECT file_id FROM case_quote_snapshot)
            """
        )
    )
    op.alter_column("file", "is_portal_quote", server_default=None)


def downgrade() -> None:
    op.drop_column("file", "is_portal_quote")
