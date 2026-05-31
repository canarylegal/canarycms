"""Native fee scale configuration (replace spreadsheet file_id)."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "o3p4q5r6s7t8"
down_revision = "n2o3p4q5r6s7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("DELETE FROM fee_scale"))
    op.drop_constraint("fee_scale_file_id_fkey", "fee_scale", type_="foreignkey")
    op.drop_column("fee_scale", "file_id")
    op.add_column(
        "fee_scale",
        sa.Column("vat_rate_bps", sa.Integer(), nullable=False, server_default="2000"),
    )
    op.alter_column("fee_scale", "vat_rate_bps", server_default=None)

    line_kind = postgresql.ENUM(
        "section_header",
        "item",
        "vat",
        "subtotal",
        "total",
        name="fee_scale_line_kind",
        create_type=True,
    )
    amount_kind = postgresql.ENUM(
        "fixed",
        "editable",
        "band",
        name="fee_scale_amount_kind",
        create_type=True,
    )
    line_kind.create(op.get_bind(), checkfirst=True)
    amount_kind.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "fee_scale_category",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fee_scale_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fee_scale.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_fee_scale_category_fee_scale_id", "fee_scale_category", ["fee_scale_id"])

    op.create_table(
        "fee_scale_band_set",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fee_scale_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fee_scale.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_fee_scale_band_set_fee_scale_id", "fee_scale_band_set", ["fee_scale_id"])

    op.create_table(
        "fee_scale_band_row",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("band_set_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fee_scale_band_set.id", ondelete="CASCADE"), nullable=False),
        sa.Column("min_value_pence", sa.BigInteger(), nullable=False),
        sa.Column("max_value_pence", sa.BigInteger(), nullable=True),
        sa.Column("amount_pence", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_fee_scale_band_row_band_set_id", "fee_scale_band_row", ["band_set_id"])

    op.create_table(
        "fee_scale_line",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fee_scale_category.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column(
            "line_kind",
            postgresql.ENUM(name="fee_scale_line_kind", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "amount_kind",
            postgresql.ENUM(name="fee_scale_amount_kind", create_type=False),
            nullable=True,
        ),
        sa.Column("default_amount_pence", sa.Integer(), nullable=True),
        sa.Column("band_set_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fee_scale_band_set.id", ondelete="SET NULL"), nullable=True),
        sa.Column("include_in_vat", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_fee_scale_line_category_id", "fee_scale_line", ["category_id"])


def downgrade() -> None:
    op.drop_index("ix_fee_scale_line_category_id", table_name="fee_scale_line")
    op.drop_table("fee_scale_line")
    op.drop_index("ix_fee_scale_band_row_band_set_id", table_name="fee_scale_band_row")
    op.drop_table("fee_scale_band_row")
    op.drop_index("ix_fee_scale_band_set_fee_scale_id", table_name="fee_scale_band_set")
    op.drop_table("fee_scale_band_set")
    op.drop_index("ix_fee_scale_category_fee_scale_id", table_name="fee_scale_category")
    op.drop_table("fee_scale_category")
    op.drop_column("fee_scale", "vat_rate_bps")
    op.add_column(
        "fee_scale",
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key("fee_scale_file_id_fkey", "fee_scale", "file", ["file_id"], ["id"], ondelete="CASCADE")
    sa.Enum(name="fee_scale_amount_kind").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="fee_scale_line_kind").drop(op.get_bind(), checkfirst=True)
