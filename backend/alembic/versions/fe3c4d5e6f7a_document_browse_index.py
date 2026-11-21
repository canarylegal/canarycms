"""Index folder-scoped visible document browsing."""
from alembic import op
from sqlalchemy import text
revision = 'fe3c4d5e6f7a'
down_revision = 'fe2b3c4d5e6f'
branch_labels = None
depends_on = None

def upgrade():
    op.create_index('ix_file_case_folder_visible', 'file', ['case_id', text('md5(folder_path)'), 'oo_compose_pending', 'parent_file_id'])

def downgrade():
    op.drop_index('ix_file_case_folder_visible', table_name='file')
