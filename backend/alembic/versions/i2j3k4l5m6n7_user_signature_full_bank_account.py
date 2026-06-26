"""User signature file + full client bank account number."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "i2j3k4l5m6n7"
down_revision = "h1i2j3k4l5m6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE file_category ADD VALUE IF NOT EXISTS 'user_signature'"))
    op.add_column(
        "firm_settings",
        sa.Column("client_bank_account_number", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "user",
        sa.Column("signature_file_id", UUID(as_uuid=True), sa.ForeignKey("file.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user", "signature_file_id")
    op.drop_column("firm_settings", "client_bank_account_number")
