"""Add optional firm-wide storage quota (bytes) for admin reporting."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "l4m5n6o7p8q9_storage_limit"
down_revision = "j2k3l4m5n6o7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("firm_settings", sa.Column("storage_limit_bytes", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("firm_settings", "storage_limit_bytes")
