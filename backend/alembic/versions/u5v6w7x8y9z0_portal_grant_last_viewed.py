"""contact_portal_grant_view — last-viewed timestamps for portal shared folders.

Revision ID: u5v6w7x8y9z0
Revises: t4u5v6w7x8y9
Create Date: 2026-09-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "u5v6w7x8y9z0"
down_revision = "t4u5v6w7x8y9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contact_portal_grant_view",
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["contact_id"], ["contact.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["grant_id"], ["contact_portal_grant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("contact_id", "grant_id"),
    )


def downgrade() -> None:
    op.drop_table("contact_portal_grant_view")
