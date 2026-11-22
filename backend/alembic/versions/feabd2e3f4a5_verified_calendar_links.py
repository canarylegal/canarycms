"""Require verified matter/calendar links; historical references remain untrusted."""
from alembic import op
import sqlalchemy as sa
revision = 'feabd2e3f4a5'
down_revision = 'feaac1d2e3f4'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('case_event', sa.Column('calendar_link_verified', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index('uq_case_event_verified_calendar_ref', 'case_event', ['calendar_event_uid'], unique=True,
        postgresql_where=sa.text('calendar_link_verified = true'))

def downgrade():
    op.drop_index('uq_case_event_verified_calendar_ref', table_name='case_event')
    op.drop_column('case_event', 'calendar_link_verified')
