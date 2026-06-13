"""Add auth_token_version on user for JWT session invalidation."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("auth_token_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("user", "auth_token_version", server_default=None)


def downgrade() -> None:
    op.drop_column("user", "auth_token_version")
