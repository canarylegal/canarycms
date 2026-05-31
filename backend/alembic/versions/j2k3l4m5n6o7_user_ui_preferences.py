"""Store per-user UI preferences (calendar view, task layout, sort order).

Revision ID: j2k3l4m5n6o7
Revises: i0j1k2l3m4n5
Create Date: 2026-05-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "j2k3l4m5n6o7"
down_revision = "i0j1k2l3m4n5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("ui_preferences", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.alter_column("user", "ui_preferences", server_default=None)


def downgrade() -> None:
    op.drop_column("user", "ui_preferences")
