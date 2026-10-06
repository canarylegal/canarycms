"""Firm Admin overrides for support inbox and portal powered-by.

Revision ID: p2a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-10-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p2a1b2c3d4e5"
down_revision = "e9f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("firm_settings", sa.Column("brand_support_inbox", sa.String(length=320), nullable=True))
    op.add_column("firm_settings", sa.Column("brand_powered_by_label", sa.String(length=200), nullable=True))
    op.add_column("firm_settings", sa.Column("brand_powered_by_url", sa.String(length=500), nullable=True))
    op.add_column(
        "firm_settings",
        sa.Column(
            "brand_powered_by_hide",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("firm_settings", "brand_powered_by_hide")
    op.drop_column("firm_settings", "brand_powered_by_url")
    op.drop_column("firm_settings", "brand_powered_by_label")
    op.drop_column("firm_settings", "brand_support_inbox")
