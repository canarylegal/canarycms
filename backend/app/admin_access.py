"""Effective admin: built-in admin role or permission category with Admin flag."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import User, UserPermissionCategory, UserRole


def user_effective_admin(user: User, db: Session) -> bool:
    if user.role == UserRole.admin:
        return True
    if user.permission_category_id is None:
        return False
    cat = db.get(UserPermissionCategory, user.permission_category_id)
    return bool(cat and cat.perm_admin)


def subject_user_effective_admin(subject: User, db: Session) -> bool:
    if subject.role == UserRole.admin:
        return True
    if subject.permission_category_id is None:
        return False
    cat = db.get(UserPermissionCategory, subject.permission_category_id)
    return bool(cat and cat.perm_admin)
