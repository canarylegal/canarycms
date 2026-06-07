"""Staff login and forgot-password rate limit counters."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v4w5x6y7z8a9"
down_revision = "u0v1w2x3y4z5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_rate_limit_entry",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("identifier", sa.String(length=320), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "identifier", name="uq_auth_rate_limit_scope_identifier"),
    )
    op.create_index("ix_auth_rate_limit_scope_identifier", "auth_rate_limit_entry", ["scope", "identifier"])


def downgrade() -> None:
    op.drop_index("ix_auth_rate_limit_scope_identifier", table_name="auth_rate_limit_entry")
    op.drop_table("auth_rate_limit_entry")
