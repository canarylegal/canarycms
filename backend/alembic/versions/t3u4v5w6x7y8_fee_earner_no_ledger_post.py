"""Remove client/office post from built-in Fee earner category."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "t3u4v5w6x7y8"
down_revision = "s2t3u4v5w6x7"
branch_labels = None
depends_on = None

_FEE_EARNER_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE user_permission_category
            SET perm_post_client = false,
                perm_post_office = false,
                updated_at = now()
            WHERE id = CAST(:fee_id AS uuid)
               OR name = 'Fee earner'
               OR name = 'Standard fee earner'
            """
        ),
        {"fee_id": _FEE_EARNER_ID},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE user_permission_category
            SET perm_post_client = true,
                perm_post_office = true,
                updated_at = now()
            WHERE id = CAST(:fee_id AS uuid)
               OR name = 'Fee earner'
               OR name = 'Standard fee earner'
            """
        ),
        {"fee_id": _FEE_EARNER_ID},
    )
