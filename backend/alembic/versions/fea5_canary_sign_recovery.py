"""Retain audited Canary Sign correction receipts; no historical backfill."""

from alembic import op
import sqlalchemy as sa

revision = "fea5e6f7a8b9"
down_revision = "fea4d5e6f7b8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "canary_sign_recovery",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("plan_sha256", sa.String(64), nullable=False),
        sa.Column("record", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_canary_sign_recovery_request_id", "canary_sign_recovery", ["request_id"]
    )
    op.execute(
        """CREATE FUNCTION protect_canary_sign_recovery() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Canary Sign recovery receipts are immutable'; END $$"""
    )
    op.execute(
        "CREATE TRIGGER immutable_canary_sign_recovery BEFORE UPDATE OR DELETE ON canary_sign_recovery FOR EACH ROW EXECUTE FUNCTION protect_canary_sign_recovery()"
    )
    op.execute(
        "CREATE TRIGGER no_truncate_canary_sign_recovery BEFORE TRUNCATE ON canary_sign_recovery FOR EACH STATEMENT EXECUTE FUNCTION protect_canary_sign_recovery()"
    )


def downgrade():
    raise RuntimeError("Retain recovery evidence; roll forward instead")
