"""Rename default fee earner category and seed Cashier permission template."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "b0c1d2e3f4a5"
branch_labels = None
depends_on = None

_FEE_EARNER_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
_CASHIER_ID = "b2c3d4e5-f6a7-8901-bcde-f12345678901"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE user_permission_category
            SET name = 'Fee earner', updated_at = now()
            WHERE id = CAST(:fee_id AS uuid)
               OR name = 'Standard fee earner'
            """
        ),
        {"fee_id": _FEE_EARNER_ID},
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO user_permission_category (
                id, name,
                perm_fee_earner, perm_post_client, perm_post_office,
                perm_approve_payments, perm_approve_invoices, perm_admin,
                created_at, updated_at
            )
            SELECT
                CAST(:cashier_id AS uuid),
                'Cashier',
                false, true, true,
                true, true, false,
                now(), now()
            WHERE NOT EXISTS (
                SELECT 1 FROM user_permission_category
                WHERE id = CAST(:cashier_id AS uuid) OR name = 'Cashier'
            )
            """
        ),
        {"cashier_id": _CASHIER_ID},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE user_permission_category
            SET name = 'Standard fee earner', updated_at = now()
            WHERE id = CAST(:fee_id AS uuid) AND name = 'Fee earner'
            """
        ),
        {"fee_id": _FEE_EARNER_ID},
    )
    conn.execute(
        sa.text(
            """
            DELETE FROM user_permission_category
            WHERE id = CAST(:cashier_id AS uuid)
              AND NOT EXISTS (
                SELECT 1 FROM "user" u WHERE u.permission_category_id = CAST(:cashier_id AS uuid)
              )
            """
        ),
        {"cashier_id": _CASHIER_ID},
    )
