"""Singleton email_integration_settings (mailto vs Graph + optional Entra fields)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p3q4r5s6t7u8"
down_revision = "n7o8p9q0r1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_integration_settings",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("integration_mode", sa.String(length=32), nullable=False, server_default="microsoft_graph"),
        sa.Column("graph_tenant_id", sa.Text(), nullable=True),
        sa.Column("graph_client_id", sa.Text(), nullable=True),
        sa.Column("graph_client_secret_enc", sa.Text(), nullable=True),
        sa.Column("outlook_web_mail_base", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute("INSERT INTO email_integration_settings (id, integration_mode) VALUES (1, 'microsoft_graph')")


def downgrade() -> None:
    op.drop_table("email_integration_settings")
