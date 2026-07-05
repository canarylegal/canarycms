"""Tests for built-in permission category bootstrap."""

from __future__ import annotations

import uuid

from app.models import UserPermissionCategory
from app.permission_category_bootstrap import (
    CASHIER_CATEGORY_ID,
    CASHIER_CATEGORY_NAME,
    FEE_EARNER_CATEGORY_ID,
    FEE_EARNER_CATEGORY_NAME,
    ensure_builtin_permission_categories,
    is_builtin_category_id,
)


class _FakeSession:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, UserPermissionCategory] = {}
        self.committed = False

    def get(self, _model, key: uuid.UUID):
        return self.rows.get(key)

    def execute(self, _stmt):
        return self

    def scalar_one_or_none(self):
        return None

    def add(self, row: UserPermissionCategory) -> None:
        self.rows[row.id] = row

    def commit(self) -> None:
        self.committed = True


def test_is_builtin_category_id() -> None:
    assert is_builtin_category_id(FEE_EARNER_CATEGORY_ID)
    assert is_builtin_category_id(CASHIER_CATEGORY_ID)
    assert not is_builtin_category_id(uuid.uuid4())


def test_ensure_builtin_permission_categories_inserts_missing() -> None:
    db = _FakeSession()
    ensure_builtin_permission_categories(db)  # type: ignore[arg-type]
    assert db.committed
    assert FEE_EARNER_CATEGORY_ID in db.rows
    assert CASHIER_CATEGORY_ID in db.rows
    fee = db.rows[FEE_EARNER_CATEGORY_ID]
    cashier = db.rows[CASHIER_CATEGORY_ID]
    assert fee.name == FEE_EARNER_CATEGORY_NAME
    assert fee.perm_fee_earner is True
    assert fee.perm_post_anticipated is True
    assert fee.perm_approve_payments is False
    assert cashier.name == CASHIER_CATEGORY_NAME
    assert cashier.perm_post_anticipated is False
    assert cashier.perm_approve_payments is True
    assert cashier.perm_approve_invoices is True
