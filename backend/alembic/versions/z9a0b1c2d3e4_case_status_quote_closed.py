"""Add case_status enum value quote_closed for quotes closed without instructing."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "z9a0b1c2d3e4"
down_revision = "y8z9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE case_status ADD VALUE IF NOT EXISTS 'quote_closed'"))


def downgrade() -> None:
    raise NotImplementedError
