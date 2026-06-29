"""Category-based permissions; admins always pass."""


from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.models import User, UserPermissionCategory, UserRole
from app.permission_checks import (
    assert_may_be_fee_earner,
    assert_may_post_ledger,
    user_may_access_accounts_workspace,
    user_may_be_fee_earner,
    user_may_post_client,
    user_may_post_office,
)
from app.schemas import LedgerPostCreate


def test_uncategorised_user_cannot_post_ledger() -> None:
    user = User(id=uuid.uuid4(), role=UserRole.user, permission_category_id=None)
    db = MagicMock()
    db.get.return_value = None
    payload = LedgerPostCreate(
        client_direction="credit",
        office_direction=None,
        amount_pence=10000,
        description="Test",
    )
    with pytest.raises(HTTPException) as exc:
        assert_may_post_ledger(user, payload, db)
    assert exc.value.status_code == 403


def test_category_without_client_post_denied() -> None:
    cat_id = uuid.uuid4()
    user = User(id=uuid.uuid4(), role=UserRole.user, permission_category_id=cat_id)
    cat = UserPermissionCategory(
        id=cat_id,
        name="Read only",
        perm_post_client=False,
        perm_post_office=True,
    )
    db = MagicMock()
    db.get.return_value = cat
    payload = LedgerPostCreate(
        client_direction="credit",
        office_direction=None,
        amount_pence=5000,
        description="Test",
    )
    with pytest.raises(HTTPException) as exc:
        assert_may_post_ledger(user, payload, db)
    assert exc.value.status_code == 403
    assert "client account" in str(exc.value.detail).lower()


def test_user_with_perm_fee_earner_may_be_fee_earner() -> None:
    cat_id = uuid.uuid4()
    user = User(id=uuid.uuid4(), role=UserRole.user, permission_category_id=cat_id)
    cat = UserPermissionCategory(id=cat_id, name="Fee earner", perm_fee_earner=True)
    db = MagicMock()
    db.get.return_value = cat
    assert user_may_be_fee_earner(user, db) is True


def test_user_without_perm_fee_earner_may_not_be_fee_earner() -> None:
    cat_id = uuid.uuid4()
    user = User(id=uuid.uuid4(), role=UserRole.user, permission_category_id=cat_id)
    cat = UserPermissionCategory(id=cat_id, name="Secretary", perm_fee_earner=False)
    db = MagicMock()
    db.get.return_value = cat
    assert user_may_be_fee_earner(user, db) is False
    with pytest.raises(HTTPException) as exc:
        assert_may_be_fee_earner(user, db)
    assert exc.value.status_code == 400


def test_built_in_admin_may_be_fee_earner_without_category() -> None:
    user = User(id=uuid.uuid4(), role=UserRole.admin, permission_category_id=None)
    db = MagicMock()
    assert user_may_be_fee_earner(user, db) is True


def test_cashier_may_access_accounts_workspace() -> None:
    cat_id = uuid.uuid4()
    user = User(id=uuid.uuid4(), role=UserRole.user, permission_category_id=cat_id)
    cat = UserPermissionCategory(
        id=cat_id,
        name="Cashier",
        perm_fee_earner=False,
        perm_approve_payments=True,
        perm_approve_invoices=True,
    )
    db = MagicMock()
    db.get.return_value = cat
    assert user_may_access_accounts_workspace(user, db) is True


def test_fee_earner_without_approve_cannot_access_accounts_workspace() -> None:
    cat_id = uuid.uuid4()
    user = User(id=uuid.uuid4(), role=UserRole.user, permission_category_id=cat_id)
    cat = UserPermissionCategory(id=cat_id, name="Fee earner", perm_fee_earner=True, perm_approve_payments=False)
    db = MagicMock()
    db.get.return_value = cat
    assert user_may_access_accounts_workspace(user, db) is False


def test_perm_admin_without_post_client_cannot_post_client() -> None:
    cat_id = uuid.uuid4()
    user = User(id=uuid.uuid4(), role=UserRole.user, permission_category_id=cat_id)
    cat = UserPermissionCategory(
        id=cat_id,
        name="Admin only",
        perm_admin=True,
        perm_post_client=False,
        perm_post_office=True,
    )
    db = MagicMock()
    db.get.return_value = cat
    assert user_may_post_client(user, db) is False
    assert user_may_post_office(user, db) is True
    payload = LedgerPostCreate(
        client_direction="credit",
        office_direction=None,
        amount_pence=5000,
        description="Test",
    )
    with pytest.raises(HTTPException) as exc:
        assert_may_post_ledger(user, payload, db)
    assert exc.value.status_code == 403
    assert "client account" in str(exc.value.detail).lower()


def test_perm_admin_without_post_office_cannot_post_office() -> None:
    cat_id = uuid.uuid4()
    user = User(id=uuid.uuid4(), role=UserRole.user, permission_category_id=cat_id)
    cat = UserPermissionCategory(
        id=cat_id,
        name="Admin only",
        perm_admin=True,
        perm_post_client=True,
        perm_post_office=False,
    )
    db = MagicMock()
    db.get.return_value = cat
    payload = LedgerPostCreate(
        client_direction=None,
        office_direction="debit",
        amount_pence=5000,
        description="Test",
    )
    with pytest.raises(HTTPException) as exc:
        assert_may_post_ledger(user, payload, db)
    assert exc.value.status_code == 403
    assert "office account" in str(exc.value.detail).lower()
