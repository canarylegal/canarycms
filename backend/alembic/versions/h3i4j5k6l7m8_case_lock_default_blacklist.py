"""Default case access to blacklist (restricted); retire lock_mode none."""

from alembic import op


revision = "h3i4j5k6l7m8"
down_revision = "g2h3i4j5k6l7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE "case"
        SET lock_mode = 'blacklist', is_locked = true
        WHERE lock_mode = 'none'
        """
    )


def downgrade() -> None:
    pass
