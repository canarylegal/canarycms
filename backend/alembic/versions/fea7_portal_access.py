"""Revocable signing links and matter contact access. No historical authorization backfill."""

from alembic import op
import sqlalchemy as sa

revision = "fea7a8b9c0d1"
down_revision = "fea6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "canary_sign_recipient",
        sa.Column("portal_access_version", sa.Integer(), nullable=True),
    )
    op.create_table(
        "portal_matter_block",
        sa.Column(
            "case_id",
            sa.Uuid(),
            sa.ForeignKey("case.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "contact_id",
            sa.Uuid(),
            sa.ForeignKey("contact.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    raise RuntimeError("Retain revocation history; roll forward instead")
