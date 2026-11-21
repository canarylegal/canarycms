"""Retain document recovery records and correlate save attempts."""
from alembic import op
import sqlalchemy as sa
revision = 'fe5e6f7a8b9c'
down_revision = 'fe4d5e6f7a8b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('document_recovery', sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('group_id', sa.Uuid(), nullable=False), sa.Column('file_id', sa.Uuid(), nullable=False),
        sa.Column('kind', sa.String(24), nullable=False), sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('storage_path', sa.String(2000)), sa.Column('checksum', sa.String(64)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_document_recovery_group_id', 'document_recovery', ['group_id'])
    op.create_index('ix_document_recovery_file_id', 'document_recovery', ['file_id'])
    for name,typ in [('oo_save_attempt_id',sa.Uuid()),('oo_save_document_key',sa.String(128)),
                     ('oo_save_state',sa.String(24)),('oo_save_base_version',sa.Integer())]:
        op.add_column('file',sa.Column(name,typ,nullable=True))


def downgrade():
    for name in ['oo_save_attempt_id','oo_save_document_key','oo_save_state','oo_save_base_version']:
        op.drop_column('file',name)
    op.drop_table('document_recovery')
