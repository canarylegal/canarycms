"""Install-wide search provider selection for matter Searches.

Revision ID: sp1a2b3c4d5e
Revises: qc1a2b3c4d5e
Create Date: 2026-10-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "sp1a2b3c4d5e"
down_revision: Union[str, Sequence[str], None] = "qc1a2b3c4d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "search_integration_settings",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("provider", sa.String(length=64), nullable=False, server_default="none"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    # Prefer Casera when it was already enabled on this install.
    op.execute(
        """
        INSERT INTO search_integration_settings (id, provider)
        SELECT 1,
               CASE
                 WHEN EXISTS (
                   SELECT 1 FROM casera_integration_settings
                   WHERE id = 1 AND enabled IS TRUE
                 ) THEN 'casera'
                 ELSE 'none'
               END
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.alter_column("search_integration_settings", "provider", server_default=None)


def downgrade() -> None:
    op.drop_table("search_integration_settings")
