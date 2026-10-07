"""Add files (multi-upload) to portal_form_field_type enum.

Revision ID: p8a1b2c3d4e5
Revises: p7a1b2c3d4e5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p8a1b2c3d4e5"
down_revision = "p7a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE portal_form_field_type ADD VALUE IF NOT EXISTS 'files'"))


def downgrade() -> None:
    # PostgreSQL cannot remove enum values.
    pass
