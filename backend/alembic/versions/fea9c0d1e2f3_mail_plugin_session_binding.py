"""Bind mail approvals to the authorizing staff session version.

Existing pending approvals remain NULL and fail closed; staff reconnect once.
"""
from alembic import op
import sqlalchemy as sa
revision = "fea9c0d1e2f3"
down_revision = "fea8b9c0d1e2"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("mail_plugin_auth_code", sa.Column("auth_token_version", sa.Integer(), nullable=True))

def downgrade():
    op.drop_column("mail_plugin_auth_code", "auth_token_version")
