"""ledger entry anticipated flag

Revision ID: s2t3u4v5w6x7
Revises: r1s2t3u4v5w6
Create Date: 2026-06-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "s2t3u4v5w6x7"
down_revision = "r1s2t3u4v5w6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ledger_entry",
        sa.Column("is_anticipated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.alter_column("ledger_entry", "is_anticipated", server_default=None)


def downgrade() -> None:
    op.drop_column("ledger_entry", "is_anticipated")
