"""Allow personal-calendar notifications without inventing a matter identity."""

from alembic import op
import sqlalchemy as sa

revision = "fea4d5e6f7b8"
down_revision = "fea3d4e5f6b7"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "notification_outbox", "case_id", existing_type=sa.Uuid(), nullable=True
    )


def downgrade():
    raise RuntimeError("Retain notification evidence; roll forward instead")
