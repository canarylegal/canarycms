"""Firm client portal logo on firm_settings."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "l0m1n2o3p4q5"
down_revision = "k9l0m1n2o3p4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE file_category ADD VALUE IF NOT EXISTS 'firm_portal_logo'"))
    op.add_column(
        "firm_settings",
        sa.Column("portal_logo_file_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_firm_settings_portal_logo_file_id",
        "firm_settings",
        "file",
        ["portal_logo_file_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_firm_settings_portal_logo_file_id", "firm_settings", type_="foreignkey")
    op.drop_column("firm_settings", "portal_logo_file_id")
