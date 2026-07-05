"""Add perm_post_anticipated to user permission categories."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "n1o2p3q4r5s6"
down_revision = "m0n1o2p3q4r5"
branch_labels = None
depends_on = None

_FEE_EARNER_CATEGORY_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def upgrade() -> None:
    op.add_column(
        "user_permission_category",
        sa.Column("perm_post_anticipated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.alter_column("user_permission_category", "perm_post_anticipated", server_default=None)
    op.execute(
        sa.text(
            """
            UPDATE user_permission_category
            SET perm_post_anticipated = true,
                updated_at = now()
            WHERE id = CAST(:cat_id AS uuid)
            """
        ).bindparams(cat_id=_FEE_EARNER_CATEGORY_ID)
    )


def downgrade() -> None:
    op.drop_column("user_permission_category", "perm_post_anticipated")
