"""Flag files uploaded via the client portal.

Revision ID: g8h9i0j1k2l3
Revises: f7a8b9c0d1e2
Create Date: 2026-05-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "g8h9i0j1k2l3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "file",
        sa.Column("uploaded_via_portal", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("file", "uploaded_via_portal", server_default=None)
    op.execute(
        sa.text(
            """
            UPDATE file SET uploaded_via_portal = true
            WHERE id::text IN (
                SELECT entity_id FROM audit_event
                WHERE action = 'portal.file.upload' AND entity_type = 'file' AND entity_id IS NOT NULL
            )
            """
        )
    )


def downgrade() -> None:
    op.drop_column("file", "uploaded_via_portal")
