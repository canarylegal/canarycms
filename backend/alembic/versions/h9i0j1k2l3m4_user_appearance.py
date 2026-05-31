"""Store user appearance preferences on the user account.

Revision ID: h9i0j1k2l3m4
Revises: g8h9i0j1k2l3
Create Date: 2026-05-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "h9i0j1k2l3m4"
down_revision = "g8h9i0j1k2l3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user", sa.Column("appearance_font", sa.Text(), nullable=True))
    op.add_column(
        "user",
        sa.Column("appearance_accent", sa.String(length=7), nullable=False, server_default="#2563eb"),
    )
    op.add_column(
        "user",
        sa.Column("appearance_mode", sa.String(length=8), nullable=False, server_default="light"),
    )
    op.add_column("user", sa.Column("appearance_page_bg", sa.String(length=7), nullable=True))
    op.alter_column("user", "appearance_accent", server_default=None)
    op.alter_column("user", "appearance_mode", server_default=None)


def downgrade() -> None:
    op.drop_column("user", "appearance_page_bg")
    op.drop_column("user", "appearance_mode")
    op.drop_column("user", "appearance_accent")
    op.drop_column("user", "appearance_font")
