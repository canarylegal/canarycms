"""non_billable flag on case_time_entry for nil-rated time."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "r1s2t3u4v5w6"
down_revision = "q0r1s2t3u4v5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DO $$ BEGIN
                ALTER TABLE case_time_entry
                    ADD COLUMN non_billable BOOLEAN NOT NULL DEFAULT FALSE;
            EXCEPTION
                WHEN duplicate_column THEN NULL;
            END $$;
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE case_time_entry t
            SET non_billable = TRUE
            FROM "user" u
            WHERE u.id = t.user_id
              AND (u.charge_rate_pence_per_hour IS NULL OR u.charge_rate_pence_per_hour <= 0);
            """
        )
    )


def downgrade() -> None:
    op.drop_column("case_time_entry", "non_billable")
