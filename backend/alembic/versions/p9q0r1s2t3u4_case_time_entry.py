"""case_time_entry + user charge rate for time / WIP."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p9q0r1s2t3u4"
down_revision = "j3k4l5m6n7o8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DO $$ BEGIN
                ALTER TABLE "user" ADD COLUMN charge_rate_pence_per_hour INTEGER;
            EXCEPTION
                WHEN duplicate_column THEN NULL;
            END $$;
            """
        )
    )
    bind.execute(
        sa.text(
            """
            DO $$ BEGIN
                CREATE TYPE case_time_entry_status AS ENUM ('unbilled', 'billed', 'written_off');
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )
    bind.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS case_time_entry (
                id UUID PRIMARY KEY,
                case_id UUID NOT NULL REFERENCES "case"(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
                created_by_user_id UUID NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
                work_date DATE NOT NULL,
                duration_minutes INTEGER NOT NULL,
                description TEXT NOT NULL,
                status case_time_entry_status NOT NULL DEFAULT 'unbilled',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
    )
    bind.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_case_time_entry_case_id ON case_time_entry (case_id)"))
    bind.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_case_time_entry_user_id ON case_time_entry (user_id)"))


def downgrade() -> None:
    op.drop_index("ix_case_time_entry_user_id", table_name="case_time_entry")
    op.drop_index("ix_case_time_entry_case_id", table_name="case_time_entry")
    op.drop_table("case_time_entry")
    op.drop_column("user", "charge_rate_pence_per_hour")
    sa.Enum(name="case_time_entry_status").drop(op.get_bind(), checkfirst=True)
