"""Merge code catalog table (admin-editable descriptions + Excel round-trip)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
revision = "s8t9u0v1w2"
down_revision = "q9w0e1r2t3y4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "merge_code_catalog",
        sa.Column("code", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("code"),
    )
    op.alter_column("merge_code_catalog", "sort_order", server_default=None)
    op.alter_column("merge_code_catalog", "updated_at", server_default=None)


def downgrade() -> None:
    op.drop_table("merge_code_catalog")
