"""Category-based permissions for ledger, invoices, and fee-earner assignment."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.admin_access import user_effective_admin
from app.models import User, UserPermissionCategory, UserRole
from app.schemas import LedgerPostCreate


def _category(user: User, db: Session) -> UserPermissionCategory | None:
    if user.permission_category_id is None:
        return None
    return db.get(UserPermissionCategory, user.permission_category_id)


def user_may_be_fee_earner(user: User, db: Session) -> bool:
    """True when the user may be assigned as a matter fee earner (merge codes, portal file owner, etc.)."""
    if user_effective_admin(user, db):
        return True
    cat = _category(user, db)
    return bool(cat and cat.perm_fee_earner)


def assert_may_be_fee_earner(user: User, db: Session) -> None:
    if not user_may_be_fee_earner(user, db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That user is not permitted to act as a fee earner.",
        )


def user_may_post_client(user: User, db: Session) -> bool:
    if user.role == UserRole.admin:
        return True
    cat = _category(user, db)
    return bool(cat and cat.perm_post_client)


def user_may_post_office(user: User, db: Session) -> bool:
    if user.role == UserRole.admin:
        return True
    cat = _category(user, db)
    return bool(cat and cat.perm_post_office)


def user_may_post_anticipated(user: User, db: Session) -> bool:
    if user.role == UserRole.admin:
        return True
    cat = _category(user, db)
    return bool(cat and cat.perm_post_anticipated)


def assert_may_post_anticipated(user: User, db: Session) -> None:
    if user.role == UserRole.admin:
        return
    cat = _category(user, db)
    if cat is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No permission profile is assigned to your account. Ask an administrator to assign one.",
        )
    if not cat.perm_post_anticipated:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your role is not permitted to post anticipated payments.",
        )


def assert_may_post_ledger(user: User, payload: LedgerPostCreate, db: Session) -> None:
    """Actual postings require post-client / post-office on each affected leg (category Admin alone is not enough)."""
    if user.role == UserRole.admin:
        return
    cat = _category(user, db)
    if cat is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No permission profile is assigned to your account. Ask an administrator to assign one.",
        )
    if payload.client_direction and not cat.perm_post_client:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your role is not permitted to post to the client account.",
        )
    if payload.office_direction and not cat.perm_post_office:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your role is not permitted to post to the office account.",
        )


def assert_may_approve_anticipated_ledger(
    user: User,
    *,
    client_direction: str | None,
    office_direction: str | None,
    db: Session,
) -> None:
    """Anticipated postings are confirmed by users with post rights on each affected leg."""
    if user.role == UserRole.admin:
        return
    cat = _category(user, db)
    if cat is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No permission profile is assigned to your account. Ask an administrator to assign one.",
        )
    if client_direction and not cat.perm_post_client:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your role is not permitted to approve client account postings.",
        )
    if office_direction and not cat.perm_post_office:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your role is not permitted to approve office account postings.",
        )


def assert_may_edit_ledger_pair(
    user: User,
    *,
    client_direction: str | None,
    office_direction: str | None,
    is_anticipated: bool,
    db: Session,
    posted_by_user_id: uuid.UUID | None = None,
    for_reject: bool = False,
) -> None:
    """Edit/reject unapproved postings.

    Anticipated: amend/cancel by original author or users with post anticipated; cashiers with
    client/office post rights may reject (not amend) before approval.
    """
    if is_anticipated and posted_by_user_id is not None and user.id == posted_by_user_id:
        return
    if not is_anticipated and user_effective_admin(user, db):
        return
    cat = _category(user, db)
    if cat is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No permission profile is assigned to your account. Ask an administrator to assign one.",
        )
    if is_anticipated:
        if user.role == UserRole.admin:
            return
        if cat.perm_post_anticipated:
            return
        if for_reject:
            if client_direction and cat.perm_post_client:
                return
            if office_direction and cat.perm_post_office:
                return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your role is not permitted to edit anticipated payments.",
        )
    if not cat.perm_approve_payments:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to edit ledger postings.",
        )


def user_may_approve_ledger(user: User, db: Session) -> bool:
    if user_effective_admin(user, db):
        return True
    cat = _category(user, db)
    return bool(cat and cat.perm_approve_payments)


def user_may_approve_invoice(user: User, db: Session) -> bool:
    if user_effective_admin(user, db):
        return True
    cat = _category(user, db)
    return bool(cat and cat.perm_approve_invoices)


def user_may_access_accounts_workspace(user: User, db: Session) -> bool:
    """Firm-wide accounts desk: admins and cashiers (ledger/invoice approvers)."""
    if user_effective_admin(user, db):
        return True
    cat = _category(user, db)
    return bool(cat and (cat.perm_approve_payments or cat.perm_approve_invoices))
