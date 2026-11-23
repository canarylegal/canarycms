"""Optional upload quarantine; historical files remain explicitly unscanned."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = 'feadf4a5b6c7'
down_revision = 'feace3f4a5b6'
branch_labels = None
depends_on = None

def upgrade():
    for column in [
        sa.Column('scan_state', sa.String(20), nullable=False, server_default='unscanned'),
        sa.Column('scan_quarantine_key', sa.String(32)),
        sa.Column('scan_checksum', sa.String(64)),
        sa.Column('scan_context', JSONB),
        sa.Column('scan_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('scan_retry_at', sa.DateTime(timezone=True)),
        sa.Column('scan_finished_at', sa.DateTime(timezone=True)),
        sa.Column('scan_error', sa.String(80)),
    ]: op.add_column('file', column)
    op.create_check_constraint('ck_file_scan_state', 'file', "scan_state IN ('unscanned','pending','clean','blocked','error')")
    op.create_index('ix_file_scan_queue', 'file', ['scan_state','scan_retry_at'],
                    postgresql_where=sa.text("scan_state IN ('pending','error')"))

def downgrade():
    raise RuntimeError('Resolve quarantined uploads before any coordinated rollback')
