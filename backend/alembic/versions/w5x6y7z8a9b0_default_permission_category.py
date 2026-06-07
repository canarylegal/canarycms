"""Seed default permission category and assign uncategorised staff users."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "w5x6y7z8a9b0"
down_revision = "v4w5x6y7z8a9"
branch_labels = None
depends_on = None

_DEFAULT_CATEGORY_ID = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def upgrade() -> None:
    conn = op.get_bind()
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
                CAST(:cat_id AS uuid),
                'Standard fee earner',
                true, true, true,
                false, false, false,
                now(), now()
            WHERE NOT EXISTS (
                SELECT 1 FROM user_permission_category WHERE name = 'Standard fee earner'
            )
            """
        ),
        {"cat_id": str(_DEFAULT_CATEGORY_ID)},
    )
    conn.execute(
        sa.text(
            """
            UPDATE "user" u
            SET permission_category_id = c.id,
                updated_at = now()
            FROM user_permission_category c
            WHERE c.name = 'Standard fee earner'
              AND u.permission_category_id IS NULL
              AND u.role = 'user'
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE "user" u
            SET permission_category_id = NULL,
                updated_at = now()
            FROM user_permission_category c
            WHERE c.name = 'Standard fee earner'
              AND u.permission_category_id = c.id
            """
        )
    )
    conn.execute(
        sa.text("DELETE FROM user_permission_category WHERE name = 'Standard fee earner'")
    )
