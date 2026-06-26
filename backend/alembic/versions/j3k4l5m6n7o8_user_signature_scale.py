"""User signature scale (1–10, default 7 = current 2 inch width)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "j3k4l5m6n7o8"
down_revision = "i2j3k4l5m6n7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("signature_scale", sa.Integer(), nullable=False, server_default="7"),
    )
    op.alter_column("user", "signature_scale", server_default=None)


def downgrade() -> None:
    op.drop_column("user", "signature_scale")
