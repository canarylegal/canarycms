"""Add checkbox to portal_form_field_type enum.

Revision ID: p7a1b2c3d4e5
Revises: p6a1b2c3d4e5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p7a1b2c3d4e5"
down_revision = "p6a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE portal_form_field_type ADD VALUE IF NOT EXISTS 'checkbox'"))


def downgrade() -> None:
    # PostgreSQL cannot remove enum values.
    pass
