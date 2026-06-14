"""Built-in permission category templates shipped with every Canary deployment."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import UserPermissionCategory

FEE_EARNER_CATEGORY_ID = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
CASHIER_CATEGORY_ID = uuid.UUID("b2c3d4e5-f6a7-8901-bcde-f12345678901")

FEE_EARNER_CATEGORY_NAME = "Fee earner"
CASHIER_CATEGORY_NAME = "Cashier"

# Legacy name from the first default-category migration (renamed on upgrade).
LEGACY_FEE_EARNER_CATEGORY_NAME = "Standard fee earner"


@dataclass(frozen=True)
class BuiltinCategorySpec:
    id: uuid.UUID
    name: str
    perm_fee_earner: bool
    perm_post_client: bool
    perm_post_office: bool
    perm_approve_payments: bool
    perm_approve_invoices: bool
    perm_admin: bool


BUILTIN_CATEGORY_SPECS: tuple[BuiltinCategorySpec, ...] = (
    BuiltinCategorySpec(
        id=FEE_EARNER_CATEGORY_ID,
        name=FEE_EARNER_CATEGORY_NAME,
        perm_fee_earner=True,
        perm_post_client=False,
        perm_post_office=False,
        perm_approve_payments=False,
        perm_approve_invoices=False,
        perm_admin=False,
    ),
    BuiltinCategorySpec(
        id=CASHIER_CATEGORY_ID,
        name=CASHIER_CATEGORY_NAME,
        perm_fee_earner=False,
        perm_post_client=True,
        perm_post_office=True,
        perm_approve_payments=True,
        perm_approve_invoices=True,
        perm_admin=False,
    ),
)

BUILTIN_CATEGORY_IDS = frozenset(spec.id for spec in BUILTIN_CATEGORY_SPECS)


def is_builtin_category_id(category_id: uuid.UUID) -> bool:
    return category_id in BUILTIN_CATEGORY_IDS


def default_fee_earner_category_id() -> uuid.UUID:
    return FEE_EARNER_CATEGORY_ID


def _insert_spec(db: Session, spec: BuiltinCategorySpec, *, now: datetime) -> None:
    db.add(
        UserPermissionCategory(
            id=spec.id,
            name=spec.name,
            perm_fee_earner=spec.perm_fee_earner,
            perm_post_client=spec.perm_post_client,
            perm_post_office=spec.perm_post_office,
            perm_approve_payments=spec.perm_approve_payments,
            perm_approve_invoices=spec.perm_approve_invoices,
            perm_admin=spec.perm_admin,
            created_at=now,
            updated_at=now,
        )
    )


def ensure_builtin_permission_categories(db: Session) -> None:
    """Ensure built-in category rows exist. Does not reset permissions admins have changed."""
    now = datetime.now(timezone.utc)
    changed = False
    for spec in BUILTIN_CATEGORY_SPECS:
        row = db.get(UserPermissionCategory, spec.id)
        if row is not None:
            continue
        name_taken = (
            db.execute(select(UserPermissionCategory.id).where(UserPermissionCategory.name == spec.name))
            .scalar_one_or_none()
        )
        if name_taken is not None:
            continue
        _insert_spec(db, spec, now=now)
        changed = True
    if changed:
        db.commit()
