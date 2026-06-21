"""Repair portal_form_template_field.select_options when y8 migration partially applied.

The original y8 migration called connection.commit() mid-upgrade, which could leave
databases at head with portal_form_field_type.select present but select_options missing.
This migration is idempotent and safe on fresh installs (column already added by y8).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b1c2d3e4f5a6"
down_revision = "a0b1c2d3e4f5"
branch_labels = None
depends_on = None


def _select_options_column_exists(connection) -> bool:
    return (
        connection.execute(
            sa.text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'portal_form_template_field'
                  AND column_name = 'select_options'
                """
            )
        ).scalar()
        is not None
    )


def upgrade() -> None:
    connection = op.get_bind()
    if _select_options_column_exists(connection):
        return

    with op.get_context().autocommit_block():
        op.execute(sa.text("ALTER TYPE portal_form_field_type ADD VALUE IF NOT EXISTS 'select'"))

    op.add_column(
        "portal_form_template_field",
        sa.Column(
            "select_options",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE portal_form_template_field
            SET field_type = 'select',
                select_options = '["Yes", "No"]'::jsonb
            WHERE field_type = 'yes_no'
            """
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    if not _select_options_column_exists(connection):
        return
    op.execute(
        sa.text(
            """
            UPDATE portal_form_template_field
            SET field_type = 'yes_no',
                select_options = '[]'::jsonb
            WHERE field_type = 'select'
            """
        )
    )
    op.drop_column("portal_form_template_field", "select_options")
