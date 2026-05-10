import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.admin_access import subject_user_effective_admin, user_effective_admin
from app.db import get_db
from app.deps import get_current_user, require_case_access
from app.models import Case, CaseAccessMode, CaseAccessRule, CaseLockMode, User
from app.audit import log_event


router = APIRouter(prefix="/cases/{case_id}/access", tags=["case-access"])


class UpsertCaseAccessRule(BaseModel):
    user_id: uuid.UUID
    mode: CaseAccessMode


class CaseAccessRuleOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    user_id: uuid.UUID
    mode: CaseAccessMode


def _may_manage_access_rules(user: User, case: Case, db) -> bool:
    return user_effective_admin(user, db) or (case.fee_earner_user_id is not None and user.id == case.fee_earner_user_id)


def _sync_case_access_flags(case_id: uuid.UUID, db: Session) -> None:
    db.flush()
    case = db.get(Case, case_id)
    if not case or case.lock_mode == CaseLockMode.none:
        return
    if case.lock_mode == CaseLockMode.whitelist:
        n = db.scalar(
            select(func.count())
            .select_from(CaseAccessRule)
            .where(CaseAccessRule.case_id == case_id, CaseAccessRule.mode == CaseAccessMode.deny)
        ) or 0
        case.is_locked = int(n) > 0
    elif case.lock_mode == CaseLockMode.blacklist:
        case.is_locked = True
    case.updated_at = datetime.utcnow()
    db.add(case)


@router.get("", response_model=list[CaseAccessRuleOut])
def list_rules(
    case_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CaseAccessRuleOut]:
    require_case_access(case_id, user, db)
    rules = db.execute(select(CaseAccessRule).where(CaseAccessRule.case_id == case_id)).scalars().all()
    return [CaseAccessRuleOut.model_validate(r, from_attributes=True) for r in rules]


@router.put("", response_model=CaseAccessRuleOut)
def upsert_rule(
    case_id: uuid.UUID,
    payload: UpsertCaseAccessRule,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CaseAccessRuleOut:
    case = require_case_access(case_id, user, db)

    if not _may_manage_access_rules(user, case, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the fee earner or an administrator may change access rules.")

    target = db.get(User, payload.user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if subject_user_effective_admin(target, db) and payload.mode == CaseAccessMode.deny:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke access for administrators.",
        )
    if case.fee_earner_user_id and payload.user_id == case.fee_earner_user_id and payload.mode == CaseAccessMode.deny:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke access for the fee earner.",
        )

    if case.lock_mode == CaseLockMode.blacklist:
        if payload.mode != CaseAccessMode.allow:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="In allow-list mode, grant access with allow rules only.",
            )
    elif case.lock_mode == CaseLockMode.whitelist:
        if payload.mode != CaseAccessMode.deny:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="In open-by-default mode, remove access with deny rules only.",
            )
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Set an access mode on the matter before editing rules.")

    existing = (
        db.execute(
            select(CaseAccessRule).where(
                CaseAccessRule.case_id == case_id,
                CaseAccessRule.user_id == payload.user_id,
            )
        )
        .scalars()
        .one_or_none()
    )
    if existing:
        existing.mode = payload.mode
        db.add(existing)
        _sync_case_access_flags(case_id, db)
        db.commit()
        db.refresh(existing)
        log_event(
            db,
            actor_user_id=user.id,
            action="case.access.upsert",
            entity_type="case_access_rule",
            entity_id=str(existing.id),
            meta={"case_id": str(case_id), "user_id": str(payload.user_id), "mode": payload.mode.value},
        )
        return CaseAccessRuleOut.model_validate(existing, from_attributes=True)

    rule = CaseAccessRule(case_id=case_id, user_id=payload.user_id, mode=payload.mode)
    db.add(rule)
    _sync_case_access_flags(case_id, db)
    db.commit()
    db.refresh(rule)
    log_event(
        db,
        actor_user_id=user.id,
        action="case.access.upsert",
        entity_type="case_access_rule",
        entity_id=str(rule.id),
        meta={"case_id": str(case_id), "user_id": str(payload.user_id), "mode": payload.mode.value},
    )
    return CaseAccessRuleOut.model_validate(rule, from_attributes=True)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    case_id: uuid.UUID,
    user_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    case = require_case_access(case_id, user, db)
    if not _may_manage_access_rules(user, case, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the fee earner or an administrator may change access rules.")

    res = db.execute(
        delete(CaseAccessRule).where(CaseAccessRule.case_id == case_id, CaseAccessRule.user_id == user_id)
    )
    if res.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    _sync_case_access_flags(case_id, db)
    db.commit()
    log_event(
        db,
        actor_user_id=user.id,
        action="case.access.delete",
        entity_type="case_access_rule",
        entity_id=f"{case_id}:{user_id}",
        meta={"case_id": str(case_id), "user_id": str(user_id)},
    )
    return None
