"""case_event: all-day flag + optional start time (UK wall clock for timed rows)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p6q7r8s9t0"
down_revision = "r5s6t7u8v9w0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "case_event",
        sa.Column("event_all_day", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column("case_event", sa.Column("event_start_time", sa.Time(), nullable=True))
    op.alter_column("case_event", "event_all_day", server_default=None)


def downgrade() -> None:
    op.drop_column("case_event", "event_start_time")
    op.drop_column("case_event", "event_all_day")
