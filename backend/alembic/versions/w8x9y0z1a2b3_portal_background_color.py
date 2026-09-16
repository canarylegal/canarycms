"""Add firm portal background colour (client portal canvas).

Revision ID: w8x9y0z1a2b3
Revises: v6w7x8y9z0a1
Create Date: 2026-09-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "w8x9y0z1a2b3"
down_revision = "v6w7x8y9z0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "firm_settings",
        sa.Column("portal_background_color", sa.String(length=7), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("firm_settings", "portal_background_color")
