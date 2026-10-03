"""Purge portal grants scoped to matter root (empty folder_path).

Revision ID: x1y2z3a4b5c6
Revises: w8x9y0z1a2b3
Create Date: 2026-10-03

Matter root must never be shared via the client portal.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "x1y2z3a4b5c6"
down_revision = "w8x9y0z1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM contact_portal_grant
            WHERE folder_path IS NULL OR BTRIM(folder_path) = ''
            """
        )
    )


def downgrade() -> None:
    # Irreversible data cleanup.
    pass
