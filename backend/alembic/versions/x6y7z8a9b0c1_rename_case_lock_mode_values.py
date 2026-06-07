"""Rename inverted case_lock_mode enum values to match behaviour."""

from __future__ import annotations

from alembic import op

revision = "x6y7z8a9b0c1"
down_revision = "w5x6y7z8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL 10+: rename enum labels in place (data unchanged).
    op.execute("ALTER TYPE case_lock_mode RENAME VALUE 'whitelist' TO 'open_by_default'")
    op.execute("ALTER TYPE case_lock_mode RENAME VALUE 'blacklist' TO 'allow_list'")


def downgrade() -> None:
    op.execute("ALTER TYPE case_lock_mode RENAME VALUE 'open_by_default' TO 'whitelist'")
    op.execute("ALTER TYPE case_lock_mode RENAME VALUE 'allow_list' TO 'blacklist'")
