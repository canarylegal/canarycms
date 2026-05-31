"""Store encrypted portal access code for staff retrieval.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-05-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contact_portal_access", sa.Column("code_enc", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("contact_portal_access", "code_enc")
