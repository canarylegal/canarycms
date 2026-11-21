"""Durable document creation and filing receipts."""

from alembic import op
import sqlalchemy as sa

revision = "fea2d3e4f5b6"
down_revision = "fea1d2e3f4b5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_operation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
    )


def downgrade():
    raise RuntimeError("Retain document retry receipts; roll forward instead")
