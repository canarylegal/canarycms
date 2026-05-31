"""Firm alert e-mail settings on email_integration_settings.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-05-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "email_integration_settings",
        sa.Column("alerts_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "email_integration_settings",
        sa.Column("alert_transport", sa.String(length=16), nullable=False, server_default="auto"),
    )
    op.add_column(
        "email_integration_settings",
        sa.Column("graph_send_mailbox", sa.String(length=320), nullable=True),
    )
    op.add_column(
        "email_integration_settings",
        sa.Column("graph_send_from_name", sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("email_integration_settings", "graph_send_from_name")
    op.drop_column("email_integration_settings", "graph_send_mailbox")
    op.drop_column("email_integration_settings", "alert_transport")
    op.drop_column("email_integration_settings", "alerts_enabled")
