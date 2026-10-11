"""Add document_key to file_edit_session for ONLYOFFICE callback binding.

Revision ID: fe1a2b3c4d5e
Revises: ba1c2d3e4f5g
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "fe1a2b3c4d5e"
down_revision: Union[str, Sequence[str], None] = "ba1c2d3e4f5g"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "file_edit_session",
        sa.Column("document_key", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("file_edit_session", "document_key")
