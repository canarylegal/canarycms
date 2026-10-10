"""Casera setting: e-mail fee earner when a search result is ready.

Revision ID: sc3a2b3c4d5e
Revises: sc2a2b3c4d5e
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "sc3a2b3c4d5e"
down_revision: Union[str, Sequence[str], None] = "sc2a2b3c4d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "casera_integration_settings" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("casera_integration_settings")}
    if "email_on_result_ready" not in cols:
        op.add_column(
            "casera_integration_settings",
            sa.Column(
                "email_on_result_ready",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "casera_integration_settings" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("casera_integration_settings")}
    if "email_on_result_ready" in cols:
        op.drop_column("casera_integration_settings", "email_on_result_ready")
