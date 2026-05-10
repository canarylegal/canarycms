"""Add file.source_mail_date (RFC822 Date) for document list / Created column on e-mail."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "r5s6t7u8v9w0"
down_revision = "p3q4r5s6t7u8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("file", sa.Column("source_mail_date", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("file", "source_mail_date")
