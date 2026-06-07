"""Per-matter portal enable flag."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "z8a9b0c1d2e3"
down_revision = "y7z8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "case",
        sa.Column("portal_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.execute(
        """
        UPDATE "case" SET portal_enabled = true
        WHERE id IN (SELECT DISTINCT case_id FROM contact_portal_grant)
        """
    )


def downgrade() -> None:
    op.drop_column("case", "portal_enabled")
