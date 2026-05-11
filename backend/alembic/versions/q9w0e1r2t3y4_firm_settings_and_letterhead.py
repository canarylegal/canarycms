"""Firm settings (trading name, UK address, letterhead) + file_category firm_letterhead."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "q9w0e1r2t3y4"
down_revision = "p6q7r8s9t0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE file_category ADD VALUE IF NOT EXISTS 'firm_letterhead'"))

    # Idempotent: a partial run may have created the type without the table.
    op.execute(
        sa.text(
            """
DO $$ BEGIN
    CREATE TYPE letterhead_style AS ENUM ('preprinted', 'digital');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
"""
        )
    )

    letterhead_style_enum = postgresql.ENUM(
        "preprinted",
        "digital",
        name="letterhead_style",
        create_type=False,
    )

    op.create_table(
        "firm_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trading_name", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("registered_company_name", sa.String(length=400), nullable=True),
        sa.Column("addr_line1", sa.String(length=300), nullable=True),
        sa.Column("addr_line2", sa.String(length=300), nullable=True),
        sa.Column("town_city", sa.String(length=200), nullable=True),
        sa.Column("county", sa.String(length=150), nullable=True),
        sa.Column("postcode", sa.String(length=50), nullable=True),
        sa.Column(
            "letterhead_style",
            letterhead_style_enum,
            nullable=False,
            server_default=sa.text("'preprinted'::letterhead_style"),
        ),
        sa.Column("letterhead_file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["letterhead_file_id"], ["file.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("id = 1", name="firm_settings_singleton"),
    )
    op.execute(
        sa.text(
            "INSERT INTO firm_settings (id, trading_name, letterhead_style, updated_at) "
            "SELECT 1, '', 'preprinted'::letterhead_style, now() "
            "WHERE NOT EXISTS (SELECT 1 FROM firm_settings WHERE id = 1)"
        )
    )
    op.alter_column("firm_settings", "trading_name", server_default=None)
    op.alter_column("firm_settings", "letterhead_style", server_default=None)
    op.alter_column("firm_settings", "updated_at", server_default=None)


def downgrade() -> None:
    op.drop_table("firm_settings")
    letterhead_style_enum = postgresql.ENUM("preprinted", "digital", name="letterhead_style")
    letterhead_style_enum.drop(op.get_bind(), checkfirst=True)
    # PostgreSQL cannot remove enum label from file_category safely; leave firm_letterhead value.
