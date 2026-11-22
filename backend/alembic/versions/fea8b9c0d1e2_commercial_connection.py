"""Opt-in hosted connection foundations; no provider data moved or jobs installed."""
from alembic import op
import sqlalchemy as sa
revision = "fea8b9c0d1e2"
down_revision = "fea7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("commercial_connection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("installation_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("tenant_id", sa.Uuid()), sa.Column("origin", sa.Text()),
        sa.Column("secret_enc", sa.Text()), sa.Column("version", sa.Integer(), nullable=False))
    op.create_table("commercial_credential",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("secret_enc", sa.Text()), sa.Column("version", sa.Integer(), nullable=False))
    op.create_table("commercial_operation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("adapter", sa.String(80), nullable=False),
        sa.Column("credential_key", sa.String(80), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("payload_enc", sa.Text(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("credential_version", sa.Integer()),
        sa.Column("result_enc", sa.Text()), sa.Column("result_hash", sa.String(64)),
        sa.Column("error_code", sa.String(40)))
    op.create_table("commercial_application",
        sa.Column("operation_id", sa.Uuid(), primary_key=True),
        sa.Column("result_hash", sa.String(64), nullable=False))


def downgrade():
    raise RuntimeError("Retain transaction receipts and local credentials; roll forward instead")
