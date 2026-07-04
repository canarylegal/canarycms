"""user calendar default event color

Revision ID: m0n1o2p3q4r5
Revises: l0m1n2o3p4q5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "m0n1o2p3q4r5"
down_revision = "l0m1n2o3p4q5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_calendar", sa.Column("default_event_color", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("user_calendar", "default_event_color")
