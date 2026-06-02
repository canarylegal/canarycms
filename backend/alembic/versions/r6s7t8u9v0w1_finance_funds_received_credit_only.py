"""Mark Funds received finance categories as credit-only."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "r6s7t8u9v0w1"
down_revision = "q5r6s7t8u9v0"
branch_labels = None
depends_on = None

FUNDS_RECEIVED = "Funds received"


def upgrade() -> None:
    op.add_column(
        "finance_category_template",
        sa.Column("credit_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "finance_category",
        sa.Column("credit_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    conn = op.get_bind()
    conn.execute(
        text(
            """
            UPDATE finance_category_template
            SET credit_only = true
            WHERE lower(trim(name)) = lower(:name)
            """
        ),
        {"name": FUNDS_RECEIVED},
    )
    conn.execute(
        text(
            """
            UPDATE finance_category
            SET credit_only = true
            WHERE lower(trim(name)) = lower(:name)
               OR template_category_id IN (
                   SELECT id FROM finance_category_template WHERE credit_only = true
               )
            """
        ),
        {"name": FUNDS_RECEIVED},
    )
    conn.execute(
        text(
            """
            UPDATE finance_item_template fit
            SET direction = 'credit'
            FROM finance_category_template fct
            WHERE fit.category_id = fct.id
              AND fct.credit_only = true
              AND fit.direction <> 'credit'
            """
        )
    )
    conn.execute(
        text(
            """
            UPDATE finance_item fi
            SET direction = 'credit'
            FROM finance_category fc
            WHERE fi.category_id = fc.id
              AND fc.credit_only = true
              AND fi.direction <> 'credit'
            """
        )
    )

    op.alter_column("finance_category_template", "credit_only", server_default=None)
    op.alter_column("finance_category", "credit_only", server_default=None)


def downgrade() -> None:
    op.drop_column("finance_category", "credit_only")
    op.drop_column("finance_category_template", "credit_only")
