"""precedent.category_id nullable again for global / head / sub-wide scopes.

Revision ID: u0v1w2x3y4
Revises: s8t9u0v1w2

``j1k2l3m4n5o6`` set ``category_id`` NOT NULL after backfilling legacy rows, but the product
allows precedents scoped without a specific category (global, matter-head-wide, or sub-type-wide).
Uploads with ``category_id = NULL`` then failed with PostgreSQL NOT NULL violations → HTTP 500.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "u0v1w2x3y4"
down_revision = "s8t9u0v1w2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "precedent",
        "category_id",
        existing_type=UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "precedent",
        "category_id",
        existing_type=UUID(as_uuid=True),
        nullable=False,
    )
