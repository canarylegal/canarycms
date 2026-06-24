"""Add letter salutation fields to case_contact."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "h1i2j3k4l5m6"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "case_contact",
        sa.Column("letter_salutation", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "case_contact",
        sa.Column("letter_salutation_custom", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("case_contact", "letter_salutation_custom")
    op.drop_column("case_contact", "letter_salutation")
