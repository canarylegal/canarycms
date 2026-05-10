"""Add perm_admin to user categories; migrate legacy blacklist deny-list to whitelist."""

from alembic import op
import sqlalchemy as sa


revision = "g2h3i4j5k6l7"
down_revision = "f9a0b1c2d3e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_permission_category",
        sa.Column("perm_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.alter_column("user_permission_category", "perm_admin", server_default=None)
    # Legacy: lock_mode blacklist + is_locked meant "deny list" (everyone in except denied).
    # New: blacklist = restrictive (allow list); that old state maps to whitelist + deny rules.
    op.execute(
        """
        UPDATE "case"
        SET lock_mode = 'whitelist'
        WHERE lock_mode = 'blacklist' AND is_locked IS TRUE
        """
    )


def downgrade() -> None:
    op.drop_column("user_permission_category", "perm_admin")
