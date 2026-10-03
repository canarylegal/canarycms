"""Portal show-logo flag on firm_settings.

Revision ID: aa1b2c3d4e5f
Revises: z3a4b5c6d7e8
Create Date: 2026-10-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "aa1b2c3d4e5f"
down_revision = "z3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "firm_settings",
        sa.Column(
            "portal_logo_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("firm_settings", "portal_logo_enabled")
