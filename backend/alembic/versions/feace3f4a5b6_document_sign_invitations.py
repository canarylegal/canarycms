"""Bind new signing invitations to validated matter recipients; no login provisioning."""
from alembic import op
import sqlalchemy as sa
revision='feace3f4a5b6'
down_revision='feabd2e3f4a5'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('canary_sign_recipient',sa.Column('document_invitation_binding',sa.Text(),nullable=True))

def downgrade():
    op.drop_column('canary_sign_recipient','document_invitation_binding')
