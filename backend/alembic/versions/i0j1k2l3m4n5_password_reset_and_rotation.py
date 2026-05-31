"""Password reset tokens and mandatory password rotation policy.

Revision ID: i0j1k2l3m4n5
Revises: h9i0j1k2l3m4
Create Date: 2026-05-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "i0j1k2l3m4n5"
down_revision = "h9i0j1k2l3m4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(sa.text('UPDATE "user" SET password_changed_at = COALESCE(updated_at, created_at) WHERE password_changed_at IS NULL'))

    op.add_column(
        "firm_settings",
        sa.Column("mandate_password_rotation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("firm_settings", sa.Column("password_rotation_days", sa.Integer(), nullable=True))

    op.create_table(
        "password_reset_token",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_sha256", name="uq_password_reset_token_sha256"),
    )
    op.create_index("ix_password_reset_token_user_id", "password_reset_token", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_password_reset_token_user_id", table_name="password_reset_token")
    op.drop_table("password_reset_token")
    op.drop_column("firm_settings", "password_rotation_days")
    op.drop_column("firm_settings", "mandate_password_rotation")
    op.drop_column("user", "password_changed_at")
