"""Add unique user.initials (backfilled for existing rows).

Revision ID: m5n6o7p8q9
Revises: k4l5m6n7o8p9
Create Date: 2026-05-04
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "m5n6o7p8q9"
down_revision = "k4l5m6n7o8p9"
branch_labels = None
depends_on = None


def _derive_base_initials(display_name: str, email: str) -> str:
    dn = (display_name or "").strip()
    words = re.findall(r"[A-Za-z0-9]+", dn)
    if words:
        raw = "".join(w[0] for w in words[:6]).upper()
        return (raw[:8] or "U")
    local = (email or "").split("@")[0].strip()
    return (re.sub(r"[^A-Za-z0-9]", "", local).upper()[:8] or "U")


def upgrade() -> None:
    op.add_column("user", sa.Column("initials", sa.String(length=12), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(text('SELECT id, display_name, email FROM "user" ORDER BY created_at')).fetchall()
    used: set[str] = set()
    for uid, display_name, email in rows:
        base = _derive_base_initials(str(display_name or ""), str(email or ""))
        cand = base[:12]
        n = 1
        while cand in used:
            suffix = str(n)
            cand = f"{base[: max(1, 12 - len(suffix))]}{suffix}"
            n += 1
        used.add(cand)
        conn.execute(text('UPDATE "user" SET initials = :i WHERE id = :id'), {"i": cand, "id": uid})

    op.alter_column("user", "initials", existing_type=sa.String(length=12), nullable=False)
    op.create_unique_constraint("uq_user_initials", "user", ["initials"])


def downgrade() -> None:
    op.drop_constraint("uq_user_initials", "user", type_="unique")
    op.drop_column("user", "initials")
