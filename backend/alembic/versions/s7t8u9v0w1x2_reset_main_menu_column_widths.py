"""Clear saved main menu / quotes case table column width overrides."""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "s7t8u9v0w1x2"
down_revision = "r6s7t8u9v0w1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        text(
            """
            UPDATE "user"
            SET ui_preferences = ui_preferences - 'main_menu_column_widths'
            WHERE ui_preferences ? 'main_menu_column_widths'
            """
        )
    )


def downgrade() -> None:
    pass
