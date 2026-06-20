"""Portal form dropdown (select) field type with configurable options."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "y8z9a0b1c2d3"
down_revision = "x7y8z9a0b1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE portal_form_field_type ADD VALUE IF NOT EXISTS 'select'"))
    # PostgreSQL requires the new enum value to be committed before use in the same session.
    op.get_bind().commit()

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
    # PostgreSQL cannot remove enum values; leave 'select' on portal_form_field_type.
