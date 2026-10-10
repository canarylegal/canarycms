"""Remove inert Quotes default case menus.

Revision ID: qc1a2b3c4d5e
Revises: pb1a2b3c4d5e
Create Date: 2026-10-09
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "qc1a2b3c4d5e"
down_revision: Union[str, Sequence[str], None] = "pb1a2b3c4d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Case left nav never implemented a Quotes panel; drop leftover admin rows.
    # Prefer firm catalogue schema; fall back to public for pre-catalogue installs.
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('firm.matter_sub_type_menu') IS NOT NULL THEN
            DELETE FROM firm.matter_sub_type_menu WHERE lower(name) = 'quotes';
          ELSIF to_regclass('public.matter_sub_type_menu') IS NOT NULL THEN
            DELETE FROM public.matter_sub_type_menu WHERE lower(name) = 'quotes';
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Intentionally empty: Quotes was never a functional case menu.
    pass
