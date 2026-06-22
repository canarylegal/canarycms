"""Add user email_desktop_client (Outlook vs Thunderbird/other on desktop)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column(
            "email_desktop_client",
            sa.String(length=32),
            nullable=False,
            server_default="outlook",
        ),
    )
    op.alter_column("user", "email_desktop_client", server_default=None)


def downgrade() -> None:
    op.drop_column("user", "email_desktop_client")
