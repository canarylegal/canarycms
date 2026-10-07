"""Firm portal/sign flags + matter_sub_type portal default.

Revision ID: p6a1b2c3d4e5
Revises: p5a1b2c3d4e5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p6a1b2c3d4e5"
down_revision = "p5a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "firm_settings",
        sa.Column(
            "client_portal_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "firm_settings",
        sa.Column(
            "canary_sign_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "matter_sub_type",
        sa.Column(
            "portal_enabled_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("matter_sub_type", "portal_enabled_default")
    op.drop_column("firm_settings", "canary_sign_enabled")
    op.drop_column("firm_settings", "client_portal_enabled")
