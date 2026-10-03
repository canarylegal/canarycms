"""Portal background image + font colour on firm_settings.

Revision ID: y2z3a4b5c6d7
Revises: x1y2z3a4b5c6
Create Date: 2026-10-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "y2z3a4b5c6d7"
down_revision = "x1y2z3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE file_category ADD VALUE IF NOT EXISTS 'firm_portal_background'"))
    op.add_column(
        "firm_settings",
        sa.Column("portal_background_file_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_firm_settings_portal_background_file_id",
        "firm_settings",
        "file",
        ["portal_background_file_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "firm_settings",
        sa.Column("portal_font_color", sa.String(length=7), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("firm_settings", "portal_font_color")
    op.drop_constraint("fk_firm_settings_portal_background_file_id", "firm_settings", type_="foreignkey")
    op.drop_column("firm_settings", "portal_background_file_id")
