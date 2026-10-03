"""user.supervisor_user_id for supervising partner merge codes.

Revision ID: ab2c3d4e5f6a
Revises: aa1b2c3d4e5f
Create Date: 2026-10-03
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "ab2c3d4e5f6a"
down_revision = "aa1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("supervisor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_user_supervisor_user_id",
        "user",
        "user",
        ["supervisor_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_user_supervisor_user_id", "user", type_="foreignkey")
    op.drop_column("user", "supervisor_user_id")
