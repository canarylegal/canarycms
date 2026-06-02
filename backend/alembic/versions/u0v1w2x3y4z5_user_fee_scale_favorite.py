"""Per-user fee scale favourites."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "u0v1w2x3y4z5"
down_revision = "t9u0v1w2x3y4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_fee_scale_favorite",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("fee_scale_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["fee_scale_id"], ["fee_scale.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "fee_scale_id", name="uq_user_fee_scale_favorite"),
    )
    op.create_index("ix_user_fee_scale_favorite_user_id", "user_fee_scale_favorite", ["user_id"])
    op.create_index("ix_user_fee_scale_favorite_fee_scale_id", "user_fee_scale_favorite", ["fee_scale_id"])


def downgrade() -> None:
    op.drop_index("ix_user_fee_scale_favorite_fee_scale_id", table_name="user_fee_scale_favorite")
    op.drop_index("ix_user_fee_scale_favorite_user_id", table_name="user_fee_scale_favorite")
    op.drop_table("user_fee_scale_favorite")
