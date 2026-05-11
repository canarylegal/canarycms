"""file: oo_force_save_pending for ONLYOFFICE no-edit force-save ack

Revision ID: a3b4c5d6e7f8
Revises: u0v1w2x3y4
Create Date: 2026-05-10

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a3b4c5d6e7f8"
down_revision = "u0v1w2x3y4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "file",
        sa.Column("oo_force_save_pending", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.alter_column("file", "oo_force_save_pending", server_default=None)


def downgrade() -> None:
    op.drop_column("file", "oo_force_save_pending")
