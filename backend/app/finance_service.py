"""Finance service — admin template CRUD + case-level finance initialisation/CRUD."""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    FinanceCategory,
    FinanceCategoryTemplate,
    FinanceItem,
    FinanceItemTemplate,
    MatterSubType,
    Case,
    AuditEvent,
    CaseQuoteSnapshot,
    FeeScaleLineKind,
    File as DbFile,
)
from app.compose_quote import quote_lines_snapshot_payload
from app.fee_scale_service import preview_quote_lines
from app.schemas import (
    FinanceCategoryCreate,
    FinanceCategoryOut,
    FinanceCategoryTemplateCreate,
    FinanceCategoryTemplateOut,
    FinanceCategoryTemplateUpdate,
    FinanceCategoryUpdate,
    FinanceItemCreate,
    FinanceItemOut,
    FinanceItemTemplateCreate,
    FinanceItemTemplateOut,
    FinanceItemTemplateUpdate,
    FinanceItemUpdate,
    FinanceOut,
    FinanceTemplateOut,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cat_tmpl_out(cat: FinanceCategoryTemplate, items: list[FinanceItemTemplate]) -> FinanceCategoryTemplateOut:
    credit_only = cat.credit_only
    return FinanceCategoryTemplateOut(
        id=cat.id,
        matter_sub_type_id=cat.matter_sub_type_id,
        name=cat.name,
        sort_order=cat.sort_order,
        credit_only=credit_only,
        items=[
            FinanceItemTemplateOut(
                id=it.id,
                category_id=it.category_id,
                name=it.name,
                direction="credit" if credit_only else it.direction,
                sort_order=it.sort_order,
            )
            for it in sorted(items, key=lambda x: (x.sort_order, x.created_at))
        ],
    )


def _item_out(item: FinanceItem, *, credit_only: bool = False) -> FinanceItemOut:
    return FinanceItemOut(
        id=item.id,
        category_id=item.category_id,
        template_item_id=item.template_item_id,
        name=item.name,
        direction="credit" if credit_only else item.direction,
        amount_pence=item.amount_pence,
        vat_pence=item.vat_pence,
        sort_order=item.sort_order,
    )


def _cat_out(cat: FinanceCategory, items: list[FinanceItem]) -> FinanceCategoryOut:
    credit_only = cat.credit_only
    return FinanceCategoryOut(
        id=cat.id,
        case_id=cat.case_id,
        template_category_id=cat.template_category_id,
        name=cat.name,
        sort_order=cat.sort_order,
        credit_only=credit_only,
        items=[
            _item_out(it, credit_only=credit_only)
            for it in sorted(items, key=lambda x: (x.sort_order, x.created_at))
        ],
    )


# ---------------------------------------------------------------------------
# Admin template API
# ---------------------------------------------------------------------------

FUNDS_RECEIVED_CATEGORY_NAME = "Funds received"


def _ensure_default_finance_template_categories(sub_type_id: uuid.UUID, db: Session) -> None:
    """Seed the default 'Funds received' category when a sub-type has no finance template yet."""
    existing = db.execute(
        select(FinanceCategoryTemplate.id)
        .where(FinanceCategoryTemplate.matter_sub_type_id == sub_type_id)
        .limit(1)
    ).scalar_one_or_none()
    if existing:
        return
    now = datetime.utcnow()
    db.add(
        FinanceCategoryTemplate(
            id=uuid.uuid4(),
            matter_sub_type_id=sub_type_id,
            name=FUNDS_RECEIVED_CATEGORY_NAME,
            sort_order=0,
            credit_only=True,
            created_at=now,
            updated_at=now,
        )
    )
    db.flush()


def get_template(sub_type_id: uuid.UUID, db: Session) -> FinanceTemplateOut:
    sub = db.get(MatterSubType, sub_type_id)
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sub type not found")

    _ensure_default_finance_template_categories(sub_type_id, db)

    cats = (
        db.execute(
            select(FinanceCategoryTemplate)
            .where(FinanceCategoryTemplate.matter_sub_type_id == sub_type_id)
            .order_by(FinanceCategoryTemplate.sort_order, FinanceCategoryTemplate.created_at)
        )
        .scalars()
        .all()
    )
    cat_ids = [c.id for c in cats]
    items_by_cat: dict[uuid.UUID, list[FinanceItemTemplate]] = {c.id: [] for c in cats}
    if cat_ids:
        all_items = (
            db.execute(
                select(FinanceItemTemplate).where(FinanceItemTemplate.category_id.in_(cat_ids))
            )
            .scalars()
            .all()
        )
        for it in all_items:
            items_by_cat[it.category_id].append(it)

    return FinanceTemplateOut(
        matter_sub_type_id=sub_type_id,
        categories=[_cat_tmpl_out(c, items_by_cat[c.id]) for c in cats],
    )


def create_category_template(payload: FinanceCategoryTemplateCreate, db: Session) -> FinanceCategoryTemplateOut:
    sub = db.get(MatterSubType, payload.matter_sub_type_id)
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sub type not found")
    now = datetime.utcnow()
    cat = FinanceCategoryTemplate(
        id=uuid.uuid4(),
        matter_sub_type_id=payload.matter_sub_type_id,
        name=payload.name,
        sort_order=payload.sort_order,
        created_at=now,
        updated_at=now,
    )
    db.add(cat)
    db.flush()
    return _cat_tmpl_out(cat, [])


def update_category_template(cat_id: uuid.UUID, payload: FinanceCategoryTemplateUpdate, db: Session) -> FinanceCategoryTemplateOut:
    cat = db.get(FinanceCategoryTemplate, cat_id)
    if not cat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    if payload.name is not None:
        cat.name = payload.name
    if payload.sort_order is not None:
        cat.sort_order = payload.sort_order
    cat.updated_at = datetime.utcnow()
    db.flush()
    items = (
        db.execute(select(FinanceItemTemplate).where(FinanceItemTemplate.category_id == cat_id))
        .scalars().all()
    )
    return _cat_tmpl_out(cat, list(items))


def delete_category_template(cat_id: uuid.UUID, db: Session) -> None:
    cat = db.get(FinanceCategoryTemplate, cat_id)
    if not cat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    db.delete(cat)
    db.flush()


def create_item_template(payload: FinanceItemTemplateCreate, db: Session) -> FinanceItemTemplateOut:
    cat = db.get(FinanceCategoryTemplate, payload.category_id)
    if not cat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    now = datetime.utcnow()
    item = FinanceItemTemplate(
        id=uuid.uuid4(),
        category_id=payload.category_id,
        name=payload.name,
        direction="credit" if cat.credit_only else payload.direction,
        sort_order=payload.sort_order,
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    db.flush()
    return FinanceItemTemplateOut(
        id=item.id,
        category_id=item.category_id,
        name=item.name,
        direction=item.direction,
        sort_order=item.sort_order,
    )


def update_item_template(item_id: uuid.UUID, payload: FinanceItemTemplateUpdate, db: Session) -> FinanceItemTemplateOut:
    item = db.get(FinanceItemTemplate, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    cat = db.get(FinanceCategoryTemplate, item.category_id)
    if payload.name is not None:
        item.name = payload.name
    if payload.direction is not None:
        item.direction = "credit" if cat and cat.credit_only else payload.direction
    if payload.sort_order is not None:
        item.sort_order = payload.sort_order
    item.updated_at = datetime.utcnow()
    db.flush()
    return FinanceItemTemplateOut(
        id=item.id,
        category_id=item.category_id,
        name=item.name,
        direction=item.direction,
        sort_order=item.sort_order,
    )


def delete_item_template(item_id: uuid.UUID, db: Session) -> None:
    item = db.get(FinanceItemTemplate, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    db.delete(item)
    db.flush()


# ---------------------------------------------------------------------------
# Quote → finance helpers
# ---------------------------------------------------------------------------

_SKIP_QUOTE_KINDS = frozenset(
    {
        FeeScaleLineKind.vat.value,
        FeeScaleLineKind.subtotal.value,
        FeeScaleLineKind.total.value,
    }
)


def _sub_type_has_finance_template(sub_type_id: uuid.UUID | None, db: Session) -> bool:
    if not sub_type_id:
        return False
    row = db.execute(
        select(FinanceCategoryTemplate.id)
        .where(FinanceCategoryTemplate.matter_sub_type_id == sub_type_id)
        .limit(1)
    ).scalar_one_or_none()
    return row is not None


def _get_latest_quote_snapshot(case_id: uuid.UUID, db: Session) -> CaseQuoteSnapshot | None:
    return db.execute(
        select(CaseQuoteSnapshot)
        .where(CaseQuoteSnapshot.case_id == case_id)
        .order_by(CaseQuoteSnapshot.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _ensure_latest_quote_snapshot(case_id: uuid.UUID, db: Session) -> CaseQuoteSnapshot | None:
    """Return the latest stored quote lines, backfilling from compose audit when missing."""
    existing = _get_latest_quote_snapshot(case_id, db)
    if existing:
        return existing

    case_id_str = str(case_id)
    events = (
        db.execute(
            select(AuditEvent)
            .where(AuditEvent.action == "case.file.compose_quote")
            .order_by(AuditEvent.created_at.desc())
            .limit(100)
        )
        .scalars()
        .all()
    )
    for ev in events:
        if not ev.meta_json:
            continue
        try:
            meta = json.loads(ev.meta_json)
        except json.JSONDecodeError:
            continue
        if str(meta.get("case_id")) != case_id_str:
            continue
        fee_scale_raw = meta.get("fee_scale_id")
        if not fee_scale_raw:
            continue
        try:
            fs_id = uuid.UUID(str(fee_scale_raw))
            file_id: uuid.UUID | None = uuid.UUID(str(ev.entity_id)) if ev.entity_id else None
        except (ValueError, TypeError):
            continue
        if file_id is not None:
            frow = db.get(DbFile, file_id)
            if frow is None or frow.case_id != case_id:
                file_id = None
        try:
            _scale, computed, _ = preview_quote_lines(db, fs_id, property_value_pence=None, overrides={})
        except Exception:
            continue
        if not computed:
            continue
        now = datetime.utcnow()
        snap = CaseQuoteSnapshot(
            id=uuid.uuid4(),
            case_id=case_id,
            file_id=file_id,
            quote_lines=quote_lines_snapshot_payload(computed),
            created_at=now,
        )
        try:
            with db.begin_nested():
                db.add(snap)
                db.flush()
        except Exception:
            continue
        return snap
    return None


def _norm_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _quote_amounts_by_name(quote_lines: list) -> dict[str, tuple[int, int | None]]:
    out: dict[str, tuple[int, int | None]] = {}
    for raw in quote_lines:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("line_kind") or "")
        if kind != FeeScaleLineKind.item.value:
            continue
        amount = raw.get("amount_pence")
        if amount is None:
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        vat_raw = raw.get("vat_pence")
        vat = int(vat_raw) if vat_raw is not None else None
        out[_norm_name(name)] = (int(amount), vat)
    return out


def _seed_finance_from_quote_lines(
    case_id: uuid.UUID,
    quote_lines: list,
    db: Session,
    *,
    start_sort_order: int = 0,
    append_funds_received: bool = True,
) -> list[FinanceCategory]:
    now = datetime.utcnow()
    new_cats: list[FinanceCategory] = []
    current_cat: FinanceCategory | None = None
    cat_order = start_sort_order
    item_order = 0

    def ensure_category(name: str) -> FinanceCategory:
        nonlocal cat_order, current_cat, item_order
        cat = FinanceCategory(
            id=uuid.uuid4(),
            case_id=case_id,
            template_category_id=None,
            name=name,
            sort_order=cat_order,
            created_at=now,
            updated_at=now,
        )
        cat_order += 1
        item_order = 0
        db.add(cat)
        new_cats.append(cat)
        current_cat = cat
        return cat

    for raw in quote_lines:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("line_kind") or "")
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        if kind in _SKIP_QUOTE_KINDS:
            continue
        if kind == FeeScaleLineKind.section_header.value:
            ensure_category(name)
            continue
        if kind != FeeScaleLineKind.item.value:
            continue
        amount = raw.get("amount_pence")
        if amount is None:
            continue
        if current_cat is None:
            ensure_category("Fees")
        assert current_cat is not None
        vat_raw = raw.get("vat_pence")
        fi = FinanceItem(
            id=uuid.uuid4(),
            category_id=current_cat.id,
            template_item_id=None,
            name=name,
            direction="debit",
            amount_pence=int(amount),
            vat_pence=int(vat_raw) if vat_raw is not None else None,
            sort_order=item_order,
            created_at=now,
            updated_at=now,
        )
        item_order += 1
        db.add(fi)

    db.flush()
    if append_funds_received:
        _append_funds_received_category(case_id, db, new_cats, cat_order)
    return new_cats


def _case_has_funds_received_category(case_id: uuid.UUID, db: Session) -> FinanceCategory | None:
    for cat in db.execute(select(FinanceCategory).where(FinanceCategory.case_id == case_id)).scalars().all():
        if cat.name.strip().lower() == FUNDS_RECEIVED_CATEGORY_NAME.lower():
            return cat
    return None


def _count_updatable_finance_items(cats: list[FinanceCategory], items: list[FinanceItem]) -> int:
    credit_only_ids = {c.id for c in cats if c.credit_only}
    return sum(1 for item in items if item.category_id not in credit_only_ids)


def _append_funds_received_category(
    case_id: uuid.UUID,
    db: Session,
    cats: list[FinanceCategory],
    sort_order: int,
) -> None:
    if any(c.name.strip().lower() == FUNDS_RECEIVED_CATEGORY_NAME.lower() for c in cats):
        return
    if _case_has_funds_received_category(case_id, db):
        return
    now = datetime.utcnow()
    cat = FinanceCategory(
        id=uuid.uuid4(),
        case_id=case_id,
        template_category_id=None,
        name=FUNDS_RECEIVED_CATEGORY_NAME,
        sort_order=sort_order,
        credit_only=True,
        created_at=now,
        updated_at=now,
    )
    db.add(cat)
    cats.append(cat)
    db.flush()


def _ensure_case_funds_received_category(case_id: uuid.UUID, db: Session) -> None:
    cats = list(
        db.execute(
            select(FinanceCategory)
            .where(FinanceCategory.case_id == case_id)
            .order_by(FinanceCategory.sort_order, FinanceCategory.created_at)
        )
        .scalars()
        .all()
    )
    next_order = max((c.sort_order for c in cats), default=-1) + 1
    _append_funds_received_category(case_id, db, cats, next_order)


def _apply_quote_amounts_to_existing_finance(case_id: uuid.UUID, quote_lines: list, db: Session) -> None:
    amounts = _quote_amounts_by_name(quote_lines)
    if not amounts:
        return
    cats = (
        db.execute(select(FinanceCategory).where(FinanceCategory.case_id == case_id))
        .scalars()
        .all()
    )
    cat_ids = [c.id for c in cats]
    if not cat_ids:
        return
    items = (
        db.execute(select(FinanceItem).where(FinanceItem.category_id.in_(cat_ids)))
        .scalars()
        .all()
    )
    now = datetime.utcnow()
    for item in items:
        key = _norm_name(item.name)
        if key in amounts:
            amount, vat = amounts[key]
            item.amount_pence = amount
            item.vat_pence = vat
            item.updated_at = now


def apply_quote_to_finance(case_id: uuid.UUID, db: Session) -> FinanceOut:
    snapshot = _ensure_latest_quote_snapshot(case_id, db)
    if not snapshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No quote found for this case.")
    cats = list(
        db.execute(
            select(FinanceCategory)
            .where(FinanceCategory.case_id == case_id)
            .order_by(FinanceCategory.sort_order, FinanceCategory.created_at)
        )
        .scalars()
        .all()
    )
    cat_ids = [c.id for c in cats]
    items = (
        list(db.execute(select(FinanceItem).where(FinanceItem.category_id.in_(cat_ids))).scalars().all())
        if cat_ids
        else []
    )
    if _count_updatable_finance_items(cats, items) == 0:
        funds_cat = _case_has_funds_received_category(case_id, db)
        new_cats = _seed_finance_from_quote_lines(
            case_id,
            snapshot.quote_lines,
            db,
            append_funds_received=not funds_cat,
        )
        if funds_cat and new_cats:
            funds_cat.sort_order = max(c.sort_order for c in new_cats) + 1
            funds_cat.updated_at = datetime.utcnow()
    else:
        _apply_quote_amounts_to_existing_finance(case_id, snapshot.quote_lines, db)
        _ensure_case_funds_received_category(case_id, db)
    db.flush()
    return get_finance(case_id, db)


# ---------------------------------------------------------------------------
# Case-level finance API
# ---------------------------------------------------------------------------

def _get_or_init_finance(case_id: uuid.UUID, db: Session) -> list[FinanceCategory]:
    """Return existing case finance categories, or seed from template if none exist."""
    existing = (
        db.execute(
            select(FinanceCategory).where(FinanceCategory.case_id == case_id).order_by(
                FinanceCategory.sort_order, FinanceCategory.created_at
            )
        )
        .scalars()
        .all()
    )
    if existing:
        return list(existing)

    # First access — check if case has a matter sub-type with a template.
    case = db.get(Case, case_id)
    if not case or not case.matter_sub_type_id:
        snapshot = _ensure_latest_quote_snapshot(case_id, db)
        if snapshot:
            return _seed_finance_from_quote_lines(case_id, snapshot.quote_lines, db)
        return []

    _ensure_default_finance_template_categories(case.matter_sub_type_id, db)

    tmpl_cats = (
        db.execute(
            select(FinanceCategoryTemplate)
            .where(FinanceCategoryTemplate.matter_sub_type_id == case.matter_sub_type_id)
            .order_by(FinanceCategoryTemplate.sort_order, FinanceCategoryTemplate.created_at)
        )
        .scalars()
        .all()
    )
    if not tmpl_cats:
        snapshot = _ensure_latest_quote_snapshot(case_id, db)
        if snapshot:
            return _seed_finance_from_quote_lines(case_id, snapshot.quote_lines, db)
        return []

    cat_ids = [c.id for c in tmpl_cats]
    tmpl_items = (
        db.execute(
            select(FinanceItemTemplate)
            .where(FinanceItemTemplate.category_id.in_(cat_ids))
            .order_by(FinanceItemTemplate.sort_order, FinanceItemTemplate.created_at)
        )
        .scalars()
        .all()
    )
    items_by_cat: dict[uuid.UUID, list[FinanceItemTemplate]] = {c.id: [] for c in tmpl_cats}
    for it in tmpl_items:
        items_by_cat[it.category_id].append(it)

    now = datetime.utcnow()
    new_cats: list[FinanceCategory] = []
    for tmpl_cat in tmpl_cats:
        cat = FinanceCategory(
            id=uuid.uuid4(),
            case_id=case_id,
            template_category_id=tmpl_cat.id,
            name=tmpl_cat.name,
            sort_order=tmpl_cat.sort_order,
            credit_only=tmpl_cat.credit_only,
            created_at=now,
            updated_at=now,
        )
        db.add(cat)
        new_cats.append(cat)
        for tmpl_item in items_by_cat[tmpl_cat.id]:
            fi = FinanceItem(
                id=uuid.uuid4(),
                category_id=cat.id,
                template_item_id=tmpl_item.id,
                name=tmpl_item.name,
                direction="credit" if tmpl_cat.credit_only else tmpl_item.direction,
                amount_pence=None,
                sort_order=tmpl_item.sort_order,
                created_at=now,
                updated_at=now,
            )
            db.add(fi)

    db.flush()
    return new_cats


def _load_items_for_cats(cat_ids: list[uuid.UUID], db: Session) -> dict[uuid.UUID, list[FinanceItem]]:
    result: dict[uuid.UUID, list[FinanceItem]] = {cid: [] for cid in cat_ids}
    if not cat_ids:
        return result
    rows = (
        db.execute(select(FinanceItem).where(FinanceItem.category_id.in_(cat_ids)))
        .scalars()
        .all()
    )
    for it in rows:
        result[it.category_id].append(it)
    return result


def get_finance(case_id: uuid.UUID, db: Session) -> FinanceOut:
    case = db.get(Case, case_id)
    cats = _get_or_init_finance(case_id, db)
    has_preset = _sub_type_has_finance_template(case.matter_sub_type_id if case else None, db) or any(
        c.template_category_id for c in cats
    )
    snap = _ensure_latest_quote_snapshot(case_id, db)
    has_quote = snap is not None
    cat_ids = [c.id for c in cats]
    items_by_cat = _load_items_for_cats(cat_ids, db)
    return FinanceOut(
        case_id=case_id,
        categories=[_cat_out(c, items_by_cat[c.id]) for c in cats],
        has_finance_preset=has_preset,
        has_quote_snapshot=has_quote,
    )


def create_finance_category(case_id: uuid.UUID, payload: FinanceCategoryCreate, db: Session) -> FinanceCategoryOut:
    now = datetime.utcnow()
    cat = FinanceCategory(
        id=uuid.uuid4(),
        case_id=case_id,
        template_category_id=None,
        name=payload.name,
        sort_order=payload.sort_order,
        created_at=now,
        updated_at=now,
    )
    db.add(cat)
    db.flush()
    return _cat_out(cat, [])


def update_finance_category(case_id: uuid.UUID, cat_id: uuid.UUID, payload: FinanceCategoryUpdate, db: Session) -> FinanceCategoryOut:
    cat = db.get(FinanceCategory, cat_id)
    if not cat or cat.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    if payload.name is not None:
        cat.name = payload.name
    if payload.sort_order is not None:
        cat.sort_order = payload.sort_order
    cat.updated_at = datetime.utcnow()
    db.flush()
    items = db.execute(select(FinanceItem).where(FinanceItem.category_id == cat_id)).scalars().all()
    return _cat_out(cat, list(items))


def delete_finance_category(case_id: uuid.UUID, cat_id: uuid.UUID, db: Session) -> None:
    cat = db.get(FinanceCategory, cat_id)
    if not cat or cat.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    db.delete(cat)
    db.flush()


def create_finance_item(case_id: uuid.UUID, payload: FinanceItemCreate, db: Session) -> FinanceItemOut:
    cat = db.get(FinanceCategory, payload.category_id)
    if not cat or cat.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    now = datetime.utcnow()
    item = FinanceItem(
        id=uuid.uuid4(),
        category_id=payload.category_id,
        template_item_id=None,
        name=payload.name,
        direction="credit" if cat.credit_only else payload.direction,
        amount_pence=None,
        sort_order=payload.sort_order,
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    db.flush()
    return _item_out(item)


def update_finance_item(case_id: uuid.UUID, item_id: uuid.UUID, payload: FinanceItemUpdate, db: Session) -> FinanceItemOut:
    item = db.get(FinanceItem, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    # Verify item belongs to this case.
    cat = db.get(FinanceCategory, item.category_id)
    if not cat or cat.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    if payload.name is not None:
        item.name = payload.name
    if payload.direction is not None:
        item.direction = "credit" if cat.credit_only else payload.direction
    if payload.amount_pence is not None:
        item.amount_pence = payload.amount_pence
    elif "amount_pence" in payload.model_fields_set and payload.amount_pence is None:
        item.amount_pence = None
    if payload.vat_pence is not None:
        item.vat_pence = payload.vat_pence
    elif "vat_pence" in payload.model_fields_set and payload.vat_pence is None:
        item.vat_pence = None
    if payload.sort_order is not None:
        item.sort_order = payload.sort_order
    item.updated_at = datetime.utcnow()
    db.flush()
    return _item_out(item)


def delete_finance_item(case_id: uuid.UUID, item_id: uuid.UUID, db: Session) -> None:
    item = db.get(FinanceItem, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    cat = db.get(FinanceCategory, item.category_id)
    if not cat or cat.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    db.delete(item)
    db.flush()
