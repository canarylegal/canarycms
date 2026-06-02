"""Backfill Funds received finance categories and rename legacy Quote/Fees buckets."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "q5r6s7t8u9v0"
down_revision = "p4q5r6s7t8u9"
branch_labels = None
depends_on = None

FUNDS_RECEIVED = "Funds received"
_LEGACY_NAMES = frozenset({"quote", "fees"})
_SKIP_QUOTE_KINDS = frozenset({"vat", "subtotal", "total"})


def _norm_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _fee_scale_primary_category_name(conn, case_id: uuid.UUID) -> str | None:
    row = conn.execute(
        text(
            """
            SELECT fsc.name
            FROM "case" c
            JOIN fee_scale fs ON (
                fs.matter_sub_type_id = c.matter_sub_type_id
                OR (
                    fs.matter_sub_type_id IS NULL
                    AND fs.matter_head_type_id = c.matter_head_type_id
                )
                OR (
                    fs.matter_sub_type_id IS NULL
                    AND fs.matter_head_type_id IS NULL
                )
            )
            JOIN fee_scale_category fsc ON fsc.fee_scale_id = fs.id
            WHERE c.id = :case_id
            ORDER BY
                CASE
                    WHEN fs.matter_sub_type_id = c.matter_sub_type_id THEN 0
                    WHEN fs.matter_head_type_id = c.matter_head_type_id THEN 1
                    ELSE 2
                END,
                fsc.sort_order,
                fsc.created_at
            LIMIT 1
            """
        ),
        {"case_id": case_id},
    ).fetchone()
    return str(row[0]).strip() if row and row[0] else None


def _category_names_from_quote_lines(quote_lines: list, fallback_name: str | None) -> list[str]:
    names: list[str] = []
    current: str | None = None
    for raw in quote_lines or []:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("line_kind") or "")
        name = str(raw.get("name") or "").strip()
        if not name or kind in _SKIP_QUOTE_KINDS:
            continue
        if kind == "section_header":
            current = name
            if not names or names[-1] != name:
                names.append(name)
            continue
        if kind != "item":
            continue
        if current is None:
            if not names:
                names.append(fallback_name or "Fees")
            continue
        if not names or names[-1] != current:
            names.append(current)
    return [n for n in names if n]


def _ensure_template_funds_received(conn, now: datetime) -> None:
    sub_types = conn.execute(
        text(
            """
            SELECT mst.id
            FROM matter_sub_type mst
            WHERE NOT EXISTS (
                SELECT 1
                FROM finance_category_template fct
                WHERE fct.matter_sub_type_id = mst.id
                  AND lower(trim(fct.name)) = lower(:name)
            )
            """
        ),
        {"name": FUNDS_RECEIVED},
    ).fetchall()

    for (sub_type_id,) in sub_types:
        max_order = conn.execute(
            text(
                """
                SELECT COALESCE(MAX(sort_order), -1)
                FROM finance_category_template
                WHERE matter_sub_type_id = :sub_type_id
                """
            ),
            {"sub_type_id": sub_type_id},
        ).scalar_one()
        conn.execute(
            text(
                """
                INSERT INTO finance_category_template (
                    id, matter_sub_type_id, name, sort_order, created_at, updated_at
                ) VALUES (
                    :id, :sub_type_id, :name, :sort_order, :created_at, :updated_at
                )
                """
            ),
            {
                "id": uuid.uuid4(),
                "sub_type_id": sub_type_id,
                "name": FUNDS_RECEIVED,
                "sort_order": int(max_order) + 1,
                "created_at": now,
                "updated_at": now,
            },
        )


def _ensure_case_funds_received(conn, now: datetime) -> None:
    case_ids = conn.execute(
        text(
            """
            SELECT DISTINCT fc.case_id
            FROM finance_category fc
            WHERE NOT EXISTS (
                SELECT 1
                FROM finance_category existing
                WHERE existing.case_id = fc.case_id
                  AND lower(trim(existing.name)) = lower(:name)
            )
            """
        ),
        {"name": FUNDS_RECEIVED},
    ).fetchall()

    for (case_id,) in case_ids:
        max_order = conn.execute(
            text(
                """
                SELECT COALESCE(MAX(sort_order), -1)
                FROM finance_category
                WHERE case_id = :case_id
                """
            ),
            {"case_id": case_id},
        ).scalar_one()
        conn.execute(
            text(
                """
                INSERT INTO finance_category (
                    id, case_id, template_category_id, name, sort_order, created_at, updated_at
                ) VALUES (
                    :id, :case_id, NULL, :name, :sort_order, :created_at, :updated_at
                )
                """
            ),
            {
                "id": uuid.uuid4(),
                "case_id": case_id,
                "name": FUNDS_RECEIVED,
                "sort_order": int(max_order) + 1,
                "created_at": now,
                "updated_at": now,
            },
        )


def _rename_legacy_quote_categories(conn, now: datetime) -> None:
    rows = conn.execute(
        text(
            """
            SELECT fc.id, fc.case_id, fc.name, fc.sort_order
            FROM finance_category fc
            WHERE fc.template_category_id IS NULL
              AND lower(trim(fc.name)) IN ('quote', 'fees')
            ORDER BY fc.case_id, fc.sort_order, fc.created_at
            """
        )
    ).fetchall()

    by_case: dict[uuid.UUID, list[tuple]] = {}
    for row in rows:
        by_case.setdefault(row.case_id, []).append(row)

    for case_id, cats in by_case.items():
        snapshot = conn.execute(
            text(
                """
                SELECT quote_lines
                FROM case_quote_snapshot
                WHERE case_id = :case_id
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"case_id": case_id},
        ).fetchone()
        quote_lines = snapshot[0] if snapshot else []
        fallback = _fee_scale_primary_category_name(conn, case_id)
        expected = _category_names_from_quote_lines(quote_lines, fallback)

        legacy_cats = [c for c in cats if _norm_name(c.name) in _LEGACY_NAMES]
        if not legacy_cats:
            continue

        if len(legacy_cats) == 1 and expected:
            new_name = expected[0]
            if new_name and _norm_name(new_name) not in _LEGACY_NAMES:
                conn.execute(
                    text(
                        """
                        UPDATE finance_category
                        SET name = :name, updated_at = :updated_at
                        WHERE id = :id
                        """
                    ),
                    {"id": legacy_cats[0].id, "name": new_name, "updated_at": now},
                )
            continue

        for idx, cat in enumerate(legacy_cats):
            new_name = expected[idx] if idx < len(expected) else fallback
            if not new_name or _norm_name(new_name) in _LEGACY_NAMES:
                continue
            conn.execute(
                text(
                    """
                    UPDATE finance_category
                    SET name = :name, updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                {"id": cat.id, "name": new_name, "updated_at": now},
            )


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc)
    _ensure_template_funds_received(conn, now)
    _ensure_case_funds_received(conn, now)
    _rename_legacy_quote_categories(conn, now)


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        text(
            """
            DELETE FROM finance_category fc
            WHERE lower(trim(fc.name)) = lower(:name)
              AND fc.template_category_id IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM finance_item fi WHERE fi.category_id = fc.id
              )
            """
        ),
        {"name": FUNDS_RECEIVED},
    )
    conn.execute(
        text(
            """
            DELETE FROM finance_category_template fct
            WHERE lower(trim(fct.name)) = lower(:name)
              AND NOT EXISTS (
                  SELECT 1 FROM finance_item_template fit WHERE fit.category_id = fct.id
              )
            """
        ),
        {"name": FUNDS_RECEIVED},
    )
