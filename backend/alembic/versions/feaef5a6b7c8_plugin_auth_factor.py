"""Preserve the approving session's verification level in mail authorization."""
from alembic import op
import sqlalchemy as sa
revision = 'feaef5a6b7c8'
down_revision = 'feadf4a5b6c7'
branch_labels = None
depends_on = None

def upgrade():
    # Existing short-lived approvals conservatively require reconnection if MFA
    # is mandatory; an old receipt must never invent verified-factor evidence.
    op.add_column('mail_plugin_auth_code', sa.Column('mfa_verified', sa.Boolean(), nullable=False, server_default=sa.false()))

def downgrade():
    op.drop_column('mail_plugin_auth_code', 'mfa_verified')
