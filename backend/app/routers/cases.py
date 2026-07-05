import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

_MISSING = object()
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.admin_access import user_effective_admin
from app.permission_checks import assert_may_be_fee_earner
from app.db import get_db
from app.deps import get_current_user, require_case_access
from app.models import (
    Case,
    CaseAccessMode,
    CaseAccessRule,
    CaseLockMode,
    CaseReferenceCounter,
    CaseSource,
    CaseStatus,
    MatterHeadType,
    MatterSubType,
    MatterSubTypeMenu,
    MatterSubTypeStandardTask,
    User,
)
from app.case_reference import display_case_number
from app.schemas import CaseCreate, CaseOut, CaseUpdate, MatterSubTypeStandardTaskOut
from app.audit import log_event
from app.ledger_service import get_ledger
from app.list_search import search_cases


router = APIRouter(prefix="/cases", tags=["cases"])


def _resolve_case_source_id(
    db: Session,
    *,
    source_id: uuid.UUID | None,
    source_name: str | None,
) -> uuid.UUID | None:
    if source_id is not None:
        if db.get(CaseSource, source_id) is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Source not found.")
        return source_id
    if not source_name:
        return None
    name = source_name.strip()
    if not name:
        return None
    existing = db.execute(select(CaseSource).where(func.lower(CaseSource.name) == name.lower())).scalar_one_or_none()
    if existing:
        return existing.id
    max_order = db.scalar(select(func.coalesce(func.max(CaseSource.sort_order), -1))) or -1
    now = datetime.now(timezone.utc)
    row = CaseSource(
        id=uuid.uuid4(),
        name=name,
        sort_order=int(max_order) + 1,
        is_system=False,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row.id


def _require_active_fee_earner(db: Session, fee_earner_user_id: uuid.UUID) -> User:
    fe = db.get(User, fee_earner_user_id)
    if not fe or not fe.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fee earner must be an active user.",
        )
    assert_may_be_fee_earner(fe, db)
    return fe


def _raise_if_hidden_matter_head_for_user(
    matter_sub_type_id: uuid.UUID | None,
    matter_head_type_id: uuid.UUID | None,
    user: User,
    db: Session,
) -> None:
    if user_effective_admin(user, db):
        return
    head_id: uuid.UUID | None = None
    if matter_sub_type_id:
        sub = db.get(MatterSubType, matter_sub_type_id)
        if sub:
            head_id = sub.head_type_id
    elif matter_head_type_id:
        head_id = matter_head_type_id
    if head_id is None:
        return
    head = db.get(MatterHeadType, head_id)
    if head and head.is_hidden:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This matter head type is hidden and cannot be assigned to a matter.",
        )


def _matter_names(
    matter_sub_type_id: uuid.UUID | None,
    matter_head_type_id: uuid.UUID | None,
    db: Session,
) -> tuple[str | None, str | None]:
    """Return (sub_type_name, head_type_name). Sub-type wins for head name when both are set."""
    if matter_sub_type_id:
        sub = db.get(MatterSubType, matter_sub_type_id)
        if not sub:
            return None, None
        head = db.get(MatterHeadType, sub.head_type_id)
        return sub.name, (head.name if head else None)
    if matter_head_type_id:
        head = db.get(MatterHeadType, matter_head_type_id)
        return None, (head.name if head else None)
    return None, None


def _case_dict(
    case: Case,
    sub_name: str | None,
    head_name: str | None,
    matter_menus: list[dict] | None = None,
    source_name: str | None = None,
) -> dict:
    return {
        "id": case.id,
        "case_number": display_case_number(case.case_number, case.status),
        "client_name": case.client_name,
        "matter_description": case.title,
        "fee_earner_user_id": case.fee_earner_user_id,
        "status": case.status,
        "practice_area": case.practice_area,
        "matter_sub_type_id": case.matter_sub_type_id,
        "matter_head_type_id": case.matter_head_type_id,
        "matter_sub_type_name": sub_name,
        "matter_head_type_name": head_name,
        "matter_menus": matter_menus or [],
        "source_id": case.source_id,
        "source_name": source_name,
        "created_by": case.created_by,
        "is_locked": case.is_locked,
        "lock_mode": case.lock_mode,
        "portal_enabled": case.portal_enabled,
        "created_at": case.created_at,
        "updated_at": case.updated_at,
    }


def _menus_for_sub_types(sub_ids: set[uuid.UUID], db: Session) -> dict[uuid.UUID, list[dict]]:
    if not sub_ids:
        return {}
    rows = (
        db.execute(
            select(MatterSubTypeMenu)
            .where(MatterSubTypeMenu.sub_type_id.in_(sub_ids))
            .order_by(MatterSubTypeMenu.sub_type_id, MatterSubTypeMenu.created_at)
        )
        .scalars()
        .all()
    )
    out: dict[uuid.UUID, list[dict]] = {}
    for m in rows:
        out.setdefault(m.sub_type_id, []).append({"id": m.id, "name": m.name})
    return out


def _case_out(case: Case, db: Session) -> CaseOut:
    sub_name, head_name = _matter_names(case.matter_sub_type_id, case.matter_head_type_id, db)
    menus = (
        _menus_for_sub_types({case.matter_sub_type_id}, db).get(case.matter_sub_type_id, [])
        if case.matter_sub_type_id
        else []
    )
    source_name = None
    if case.source_id:
        src = db.get(CaseSource, case.source_id)
        source_name = src.name if src else None
    return CaseOut.model_validate(_case_dict(case, sub_name, head_name, menus, source_name))


@router.post("", response_model=CaseOut, status_code=status.HTTP_201_CREATED)
def create_case(
    payload: CaseCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CaseOut:
    # Generate 6-digit immutable reference (case_number) using a DB counter row.
    counter = db.get(CaseReferenceCounter, 1)
    if not counter:
        counter = CaseReferenceCounter(id=1, next_value=1)
        db.add(counter)
        db.commit()
        db.refresh(counter)

    # Lock the counter row for update to prevent duplicate refs.
    counter = db.execute(select(CaseReferenceCounter).where(CaseReferenceCounter.id == 1).with_for_update()).scalar_one()
    ref_num = counter.next_value
    counter.next_value = ref_num + 1
    case_number = f"{ref_num:06d}"

    sub = db.get(MatterSubType, payload.matter_sub_type_id)
    if not sub:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Matter sub-type not found")
    _raise_if_hidden_matter_head_for_user(sub.id, None, user, db)
    resolved_sub = sub.id
    resolved_head = sub.head_type_id
    _require_active_fee_earner(db, payload.fee_earner_user_id)
    resolved_source_id = _resolve_case_source_id(
        db,
        source_id=payload.source_id,
        source_name=payload.source_name,
    )

    case = Case(
        case_number=case_number,
        client_name=None,
        title=payload.matter_description,
        status=payload.status,
        practice_area=payload.practice_area,
        matter_sub_type_id=resolved_sub,
        matter_head_type_id=resolved_head,
        fee_earner_user_id=payload.fee_earner_user_id,
        source_id=resolved_source_id,
        created_by=user.id,
        is_locked=False,
        lock_mode=CaseLockMode.open_by_default,
        portal_enabled=payload.portal_enabled,
    )
    db.add(counter)
    db.add(case)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(case)
    log_event(
        db,
        actor_user_id=user.id,
        action="case.create",
        entity_type="case",
        entity_id=str(case.id),
        meta={"case_number": case.case_number, "client_name": case.client_name, "matter_description": case.title},
    )
    return _case_out(case, db)


def _cases_to_out_list(cases: list[Case], db: Session) -> list[CaseOut]:
    if not cases:
        return []
    sub_ids = {c.matter_sub_type_id for c in cases if c.matter_sub_type_id}
    head_ids: set[uuid.UUID] = {c.matter_head_type_id for c in cases if c.matter_head_type_id}
    sub_map: dict[uuid.UUID, MatterSubType] = {}
    head_map: dict[uuid.UUID, MatterHeadType] = {}
    if sub_ids:
        subs = db.execute(select(MatterSubType).where(MatterSubType.id.in_(sub_ids))).scalars().all()
        sub_map = {s.id: s for s in subs}
        head_ids |= {s.head_type_id for s in subs}
    if head_ids:
        heads = db.execute(select(MatterHeadType).where(MatterHeadType.id.in_(head_ids))).scalars().all()
        head_map = {h.id: h for h in heads}

    menu_map = _menus_for_sub_types(sub_ids, db)
    source_ids = {c.source_id for c in cases if c.source_id}
    source_map: dict[uuid.UUID, str] = {}
    if source_ids:
        src_rows = db.execute(select(CaseSource).where(CaseSource.id.in_(source_ids))).scalars().all()
        source_map = {s.id: s.name for s in src_rows}
    result: list[CaseOut] = []
    for c in cases:
        sub_name = None
        head_name = None
        if c.matter_sub_type_id and c.matter_sub_type_id in sub_map:
            sub = sub_map[c.matter_sub_type_id]
            sub_name = sub.name
            head = head_map.get(sub.head_type_id)
            head_name = head.name if head else None
        elif c.matter_head_type_id and c.matter_head_type_id in head_map:
            head_name = head_map[c.matter_head_type_id].name
        menus = menu_map.get(c.matter_sub_type_id, []) if c.matter_sub_type_id else []
        src_name = source_map.get(c.source_id) if c.source_id else None
        result.append(CaseOut.model_validate(_case_dict(c, sub_name, head_name, menus, src_name)))
    return result


@router.get("", response_model=list[CaseOut])
def list_cases(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, description="Search reference, client, description, fee earner"),
    limit: int | None = Query(default=None, ge=1, le=100),
    status: CaseStatus | None = Query(default=None),
) -> list[CaseOut]:
    q_trim = (q or "").strip()
    if q_trim:
        cases = search_cases(db, user, q=q_trim, limit=limit, status_filter=status)
        return _cases_to_out_list(cases, db)

    cases = db.execute(select(Case).order_by(Case.created_at.desc())).scalars().all()
    return _cases_to_out_list(list(cases), db)


@router.get("/{case_id}/standard-tasks", response_model=list[MatterSubTypeStandardTaskOut])
def list_standard_tasks_for_case(
    case_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MatterSubTypeStandardTaskOut]:
    case = require_case_access(case_id, user, db)
    global_rows = (
        db.execute(
            select(MatterSubTypeStandardTask).where(
                MatterSubTypeStandardTask.is_system.is_(True),
                MatterSubTypeStandardTask.matter_sub_type_id.is_(None),
            )
        )
        .scalars()
        .all()
    )
    if not case.matter_sub_type_id:
        merged = list(global_rows)
        merged.sort(key=lambda r: (r.sort_order, r.created_at))
        return [MatterSubTypeStandardTaskOut.model_validate(r, from_attributes=True) for r in merged]

    local_rows = (
        db.execute(
            select(MatterSubTypeStandardTask)
            .where(MatterSubTypeStandardTask.matter_sub_type_id == case.matter_sub_type_id)
            .where(MatterSubTypeStandardTask.is_system.is_(False))
            .order_by(MatterSubTypeStandardTask.sort_order, MatterSubTypeStandardTask.created_at)
        )
        .scalars()
        .all()
    )
    merged = list(global_rows) + list(local_rows)
    merged.sort(key=lambda r: (r.sort_order, r.created_at))
    return [MatterSubTypeStandardTaskOut.model_validate(r, from_attributes=True) for r in merged]


@router.get("/{case_id}", response_model=CaseOut)
def get_case(case_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> CaseOut:
    case = require_case_access(case_id, user, db)
    return _case_out(case, db)


@router.patch("/{case_id}", response_model=CaseOut)
def update_case(
    case_id: uuid.UUID,
    payload: CaseUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CaseOut:
    case = require_case_access(case_id, user, db)

    data = payload.model_dump(exclude_unset=True)
    # Map API field to DB field
    if "matter_description" in data:
        data["title"] = data.pop("matter_description")

    if "fee_earner_user_id" in data:
        if data["fee_earner_user_id"] is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Fee earner is required; it cannot be cleared.",
            )
        _require_active_fee_earner(db, data["fee_earner_user_id"])

    access_mode_keys = {"lock_mode", "is_locked"}
    if access_mode_keys & set(data.keys()):
        if not (
            user_effective_admin(user, db)
            or (case.fee_earner_user_id is not None and user.id == case.fee_earner_user_id)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the fee earner or an administrator may change case access mode.",
            )

    old_lock_mode = case.lock_mode
    if "lock_mode" in data and data["lock_mode"] is not None and data["lock_mode"] != old_lock_mode:
        new_lm = data["lock_mode"]
        if new_lm == CaseLockMode.none:
            db.execute(delete(CaseAccessRule).where(CaseAccessRule.case_id == case_id))
        elif new_lm == CaseLockMode.allow_list:
            db.execute(
                delete(CaseAccessRule).where(
                    CaseAccessRule.case_id == case_id,
                    CaseAccessRule.mode == CaseAccessMode.deny,
                )
            )
        elif new_lm == CaseLockMode.open_by_default:
            db.execute(
                delete(CaseAccessRule).where(
                    CaseAccessRule.case_id == case_id,
                    CaseAccessRule.mode == CaseAccessMode.allow,
                )
            )
        db.flush()
        if new_lm == CaseLockMode.allow_list:
            case.is_locked = True
        elif new_lm == CaseLockMode.open_by_default:
            n_deny = db.scalar(
                select(func.count())
                .select_from(CaseAccessRule)
                .where(CaseAccessRule.case_id == case_id, CaseAccessRule.mode == CaseAccessMode.deny)
            ) or 0
            case.is_locked = int(n_deny) > 0
        else:
            case.is_locked = False
        if "is_locked" in data:
            data.pop("is_locked", None)

    ms = data.pop("matter_sub_type_id", _MISSING)
    mh = data.pop("matter_head_type_id", _MISSING)
    if ms is not _MISSING or mh is not _MISSING:
        if ms is not _MISSING and ms is not None:
            sub = db.get(MatterSubType, ms)
            if not sub:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Matter sub-type not found")
            case.matter_sub_type_id = sub.id
            case.matter_head_type_id = sub.head_type_id
        elif ms is not _MISSING and ms is None:
            case.matter_sub_type_id = None
            if mh is not _MISSING:
                if mh is not None:
                    if db.get(MatterHeadType, mh) is None:
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Matter head type not found")
                    case.matter_head_type_id = mh
                else:
                    case.matter_head_type_id = None
            else:
                case.matter_head_type_id = None
        elif mh is not _MISSING:
            if case.matter_sub_type_id is not None:
                pass
            else:
                if mh is not None and db.get(MatterHeadType, mh) is None:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Matter head type not found")
                case.matter_head_type_id = mh

        _raise_if_hidden_matter_head_for_user(case.matter_sub_type_id, case.matter_head_type_id, user, db)

    if "status" in data and data["status"] == CaseStatus.quote:
        if case.status != CaseStatus.quote:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "A matter that is no longer a quote cannot be set back to Quote. "
                    "Use Active or another status, or keep the matter as a quote until it is instructed."
                ),
            )

    if "status" in data and data["status"] == CaseStatus.quote_closed:
        if case.status != CaseStatus.quote:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only an open quote can be closed from the Quotes menu.",
            )

    if "status" in data and data["status"] in (CaseStatus.closed, CaseStatus.archived, CaseStatus.quote_closed):
        ledger = get_ledger(case_id, db)
        c_bal = ledger.client.balance_pence
        o_bal = ledger.office.balance_pence
        if c_bal != 0 or o_bal != 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Cannot set a matter to Closed or Archived while the client or office account "
                    "has a non-zero balance."
                ),
            )

    if "source_id" in data or "source_name" in data:
        sid = data.pop("source_id") if "source_id" in data else None
        sname = data.pop("source_name") if "source_name" in data else None
        case.source_id = _resolve_case_source_id(db, source_id=sid, source_name=sname)

    for key, value in data.items():
        setattr(case, key, value)
    case.updated_at = datetime.utcnow()

    db.add(case)
    db.commit()
    db.refresh(case)
    log_event(
        db,
        actor_user_id=user.id,
        action="case.update",
        entity_type="case",
        entity_id=str(case.id),
        meta=payload.model_dump(exclude_unset=True),
    )
    return _case_out(case, db)
