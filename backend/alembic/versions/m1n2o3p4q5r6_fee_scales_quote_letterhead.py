"""Fee scales and quote letterhead settings."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "m1n2o3p4q5r6"
down_revision = "l4m5n6o7p8q9_storage_limit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fee_scale",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("reference", sa.String(length=200), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("file.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("reference", name="uq_fee_scale_reference"),
    )
    op.add_column(
        "firm_settings",
        sa.Column(
            "quote_letterhead_style",
            sa.Enum("preprinted", "digital", name="letterhead_style", create_type=False),
            nullable=False,
            server_default="preprinted",
        ),
    )
    op.add_column(
        "firm_settings",
        sa.Column("quote_letterhead_file_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_firm_settings_quote_letterhead_file_id",
        "firm_settings",
        "file",
        ["quote_letterhead_file_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_firm_settings_quote_letterhead_file_id", "firm_settings", type_="foreignkey")
    op.drop_column("firm_settings", "quote_letterhead_file_id")
    op.drop_column("firm_settings", "quote_letterhead_style")
    op.drop_table("fee_scale")
