"""Add portal session_version for revoking portal JWTs."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "t4u5v6w7x8y9"
down_revision = "s3t4u5v6w7x8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contact_portal_access",
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("contact_portal_access", "session_version", server_default=None)


def downgrade() -> None:
    op.drop_column("contact_portal_access", "session_version")
