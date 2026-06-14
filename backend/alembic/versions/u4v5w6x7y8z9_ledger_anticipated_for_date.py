"""anticipated payment expected date on ledger_entry"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "u4v5w6x7y8z9"
down_revision = "t3u4v5w6x7y8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ledger_entry", sa.Column("anticipated_for_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("ledger_entry", "anticipated_for_date")
