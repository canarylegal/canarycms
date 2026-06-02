"""Firm-wide native fee scale templates for quote compose."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.audit import log_event
from app.db import get_db
from app.deps import get_current_user
from app.docx_util import format_gbp_pence
from app.fee_scale_service import (
    _ensure_reference_unique,
    _validate_scope,
    fee_scale_matches_case,
    load_scale_graph,
    preview_quote_draft,
    preview_quote_lines,
)
from app.models import (
    FeeScale,
    FeeScaleAmountKind,
    FeeScaleBandRow,
    FeeScaleBandSet,
    FeeScaleCategory,
    FeeScaleLine,
    FeeScaleLineKind,
    FeeScaleVatTreatment,
    MatterHeadType,
    MatterSubType,
    User,
    UserFeeScaleFavorite,
)
from app.schemas import (
    FeeScaleBandRowCreate,
    FeeScaleBandRowOut,
    FeeScaleBandRowUpdate,
    FeeScaleBandSetCreate,
    FeeScaleBandSetOut,
    FeeScaleBandSetUpdate,
    FeeScaleCategoryCreate,
    FeeScaleCategoryOut,
    FeeScaleCategoryUpdate,
    FeeScaleCreate,
    FeeScaleFavoriteUpdate,
    FeeScaleDetailOut,
    FeeScaleLineCreate,
    FeeScaleLineOut,
    FeeScaleLineUpdate,
    FeeScaleOut,
    FeeScaleUpdate,
    QuotePreviewCategoryOut,
    QuotePreviewIn,
    QuotePreviewLineOut,
    QuotePreviewOut,
)

router = APIRouter(prefix="/fee-scales", tags=["fee-scales"])

GLOBAL_SCOPE = "__GLOBAL__"


def _line_out_from_computed(key: str, draft_line, computed) -> QuotePreviewLineOut:
    return QuotePreviewLineOut(
        key=key,
        line_id=draft_line.line_id,
        name=draft_line.name,
        line_kind=draft_line.line_kind,
        amount_pence=computed.amount_pence,
        amount_display=format_gbp_pence(computed.amount_pence) if computed.amount_pence is not None else None,
        editable=computed.editable,
        is_bold=computed.is_bold,
        vat_treatment=draft_line.vat_treatment,
        vat_pence=computed.vat_pence,
        amount_kind=draft_line.amount_kind,
        band_set_id=draft_line.band_set_id,
        sort_order=draft_line.sort_order,
    )


def _preview_line_out(ln) -> QuotePreviewLineOut:
    return QuotePreviewLineOut(
        line_id=ln.line_id,
        name=ln.name,
        line_kind=ln.line_kind.value,
        amount_pence=ln.amount_pence,
        vat_pence=ln.vat_pence,
        vat_treatment=ln.vat_treatment.value if ln.vat_treatment else None,
        amount_display=format_gbp_pence(ln.amount_pence) if ln.amount_pence is not None else None,
        editable=ln.editable,
        is_bold=ln.is_bold,
    )


def _scope_summary(*, head_name: str | None, sub_name: str | None, mh: uuid.UUID | None, ms: uuid.UUID | None) -> str:
    if mh is None and ms is None:
        return "Global — all cases"
    if ms is None:
        return f"All sub-types — {head_name or '—'}"
    return f"{sub_name or '—'}"


def _fee_scale_list_order():
    """Global first, then head-wide scales, then sub-type scales; alphabetical within each band."""
    scope_rank = case(
        (
            and_(FeeScale.matter_head_type_id.is_(None), FeeScale.matter_sub_type_id.is_(None)),
            0,
        ),
        (FeeScale.matter_sub_type_id.is_(None), 1),
        else_=2,
    )
    return (
        scope_rank,
        func.lower(func.coalesce(MatterHeadType.name, "")),
        func.lower(func.coalesce(MatterSubType.name, "")),
        func.lower(FeeScale.name),
    )


def _favorite_ids_for_user(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    rows = db.execute(
        select(UserFeeScaleFavorite.fee_scale_id).where(UserFeeScaleFavorite.user_id == user_id)
    ).scalars().all()
    return set(rows)


def _fee_scale_out(db: Session, scale: FeeScale, *, is_favorited: bool = False) -> FeeScaleOut:
    head_name: str | None = None
    sub_name: str | None = None
    if scale.matter_head_type_id:
        h = db.get(MatterHeadType, scale.matter_head_type_id)
        head_name = h.name if h else None
    if scale.matter_sub_type_id:
        s = db.get(MatterSubType, scale.matter_sub_type_id)
        sub_name = s.name if s else None
    return FeeScaleOut(
        id=scale.id,
        name=scale.name,
        reference=scale.reference,
        vat_rate_bps=scale.vat_rate_bps,
        matter_head_type_id=scale.matter_head_type_id,
        matter_sub_type_id=scale.matter_sub_type_id,
        matter_head_type_name=head_name,
        matter_sub_type_name=sub_name,
        scope_summary=_scope_summary(
            head_name=head_name,
            sub_name=sub_name,
            mh=scale.matter_head_type_id,
            ms=scale.matter_sub_type_id,
        ),
        is_favorited=is_favorited,
        created_at=scale.created_at,
        updated_at=scale.updated_at,
    )


def _line_out(ln: FeeScaleLine) -> FeeScaleLineOut:
    return FeeScaleLineOut(
        id=ln.id,
        category_id=ln.category_id,
        name=ln.name,
        line_kind=ln.line_kind.value,
        amount_kind=ln.amount_kind.value if ln.amount_kind else None,
        default_amount_pence=ln.default_amount_pence,
        band_set_id=ln.band_set_id,
        vat_treatment=ln.vat_treatment.value,
        sort_order=ln.sort_order,
    )


def _detail_out(
    db: Session,
    scale: FeeScale,
    categories: list[FeeScaleCategory],
    lines_by_cat: dict[uuid.UUID, list[FeeScaleLine]],
    band_sets: list[FeeScaleBandSet],
    rows_by_set: dict[uuid.UUID, list[FeeScaleBandRow]],
) -> FeeScaleDetailOut:
    base = _fee_scale_out(db, scale)
    return FeeScaleDetailOut(
        **base.model_dump(),
        categories=[
            FeeScaleCategoryOut(
                id=c.id,
                fee_scale_id=c.fee_scale_id,
                name=c.name,
                sort_order=c.sort_order,
                lines=[_line_out(ln) for ln in lines_by_cat.get(c.id, [])],
            )
            for c in categories
        ],
        band_sets=[
            FeeScaleBandSetOut(
                id=s.id,
                fee_scale_id=s.fee_scale_id,
                name=s.name,
                sort_order=s.sort_order,
                rows=[
                    FeeScaleBandRowOut(
                        id=r.id,
                        band_set_id=r.band_set_id,
                        min_value_pence=int(r.min_value_pence),
                        max_value_pence=int(r.max_value_pence) if r.max_value_pence is not None else None,
                        amount_pence=r.amount_pence,
                        sort_order=r.sort_order,
                    )
                    for r in rows_by_set.get(s.id, [])
                ],
            )
            for s in band_sets
        ],
    )


@router.get("", response_model=list[FeeScaleOut])
def list_fee_scales(
    matter_head_type_id: uuid.UUID | None = Query(None),
    matter_sub_type_id: uuid.UUID | None = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[FeeScaleOut]:
    if matter_sub_type_id is not None:
        head_id = matter_head_type_id
        if head_id is None:
            sub = db.get(MatterSubType, matter_sub_type_id)
            if sub:
                head_id = sub.head_type_id
        scope_global = and_(FeeScale.matter_head_type_id.is_(None), FeeScale.matter_sub_type_id.is_(None))
        scope_head = and_(FeeScale.matter_head_type_id == head_id, FeeScale.matter_sub_type_id.is_(None))
        scope_sub = FeeScale.matter_sub_type_id == matter_sub_type_id
        q = select(FeeScale).where(or_(scope_global, scope_head, scope_sub))
    elif matter_head_type_id is not None:
        scope_global = and_(FeeScale.matter_head_type_id.is_(None), FeeScale.matter_sub_type_id.is_(None))
        scope_head = and_(FeeScale.matter_head_type_id == matter_head_type_id, FeeScale.matter_sub_type_id.is_(None))
        q = select(FeeScale).where(or_(scope_global, scope_head))
    else:
        q = select(FeeScale)
    q = (
        q.outerjoin(MatterHeadType, FeeScale.matter_head_type_id == MatterHeadType.id)
        .outerjoin(MatterSubType, FeeScale.matter_sub_type_id == MatterSubType.id)
        .order_by(*_fee_scale_list_order())
    )
    rows = db.execute(q).scalars().all()
    fav_ids = _favorite_ids_for_user(db, user.id)
    return [_fee_scale_out(db, scale, is_favorited=scale.id in fav_ids) for scale in rows]


@router.post("", response_model=FeeScaleDetailOut, status_code=status.HTTP_201_CREATED)
def create_fee_scale(
    payload: FeeScaleCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeeScaleDetailOut:
    _validate_scope(db, payload.matter_head_type_id, payload.matter_sub_type_id)
    ref = _ensure_reference_unique(db, payload.reference.strip())
    now = datetime.utcnow()
    row = FeeScale(
        id=uuid.uuid4(),
        name=payload.name.strip(),
        reference=ref,
        vat_rate_bps=payload.vat_rate_bps,
        matter_head_type_id=payload.matter_head_type_id,
        matter_sub_type_id=payload.matter_sub_type_id,
        owner_id=user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_event(db, actor_user_id=user.id, action="fee_scale.create", entity_type="fee_scale", entity_id=str(row.id))
    scale, cats, lines_by_cat, band_sets, rows_by_set = load_scale_graph(db, row.id)
    return _detail_out(db, scale, cats, lines_by_cat, band_sets, rows_by_set)


@router.put("/{fee_scale_id}/favorite", response_model=FeeScaleOut)
def set_fee_scale_favorite(
    fee_scale_id: uuid.UUID,
    payload: FeeScaleFavoriteUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeeScaleOut:
    row = db.get(FeeScale, fee_scale_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fee scale not found")
    existing = db.execute(
        select(UserFeeScaleFavorite).where(
            UserFeeScaleFavorite.user_id == user.id,
            UserFeeScaleFavorite.fee_scale_id == fee_scale_id,
        )
    ).scalar_one_or_none()
    if payload.favorited:
        if existing is None:
            db.add(
                UserFeeScaleFavorite(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    fee_scale_id=fee_scale_id,
                    created_at=datetime.utcnow(),
                )
            )
            db.commit()
    elif existing is not None:
        db.delete(existing)
        db.commit()
    return _fee_scale_out(db, row, is_favorited=payload.favorited)


@router.get("/{fee_scale_id}", response_model=FeeScaleDetailOut)
def get_fee_scale(
    fee_scale_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeeScaleDetailOut:
    scale, cats, lines_by_cat, band_sets, rows_by_set = load_scale_graph(db, fee_scale_id)
    return _detail_out(db, scale, cats, lines_by_cat, band_sets, rows_by_set)


@router.patch("/{fee_scale_id}", response_model=FeeScaleOut)
def update_fee_scale(
    fee_scale_id: uuid.UUID,
    payload: FeeScaleUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeeScaleOut:
    row = db.get(FeeScale, fee_scale_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fee scale not found")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        row.name = data["name"].strip()
    if "reference" in data and data["reference"] is not None:
        row.reference = _ensure_reference_unique(db, data["reference"].strip(), exclude_id=fee_scale_id)
    if "vat_rate_bps" in data and data["vat_rate_bps"] is not None:
        row.vat_rate_bps = data["vat_rate_bps"]
    scope_keys = ("matter_head_type_id", "matter_sub_type_id")
    if any(k in data for k in scope_keys):
        mh = data["matter_head_type_id"] if "matter_head_type_id" in data else row.matter_head_type_id
        ms = data["matter_sub_type_id"] if "matter_sub_type_id" in data else row.matter_sub_type_id
        if mh is None:
            ms = None
        elif ms is not None:
            sub = db.get(MatterSubType, ms)
            if sub is not None:
                mh = sub.head_type_id
        _validate_scope(db, mh, ms)
        row.matter_head_type_id = mh
        row.matter_sub_type_id = ms
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    fav_ids = _favorite_ids_for_user(db, user.id)
    return _fee_scale_out(db, row, is_favorited=row.id in fav_ids)


@router.delete("/{fee_scale_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fee_scale(
    fee_scale_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    row = db.get(FeeScale, fee_scale_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fee scale not found")
    db.delete(row)
    db.commit()
    log_event(db, actor_user_id=user.id, action="fee_scale.delete", entity_type="fee_scale", entity_id=str(fee_scale_id))


@router.post("/{fee_scale_id}/preview", response_model=QuotePreviewOut)
def preview_fee_scale_quote(
    fee_scale_id: uuid.UUID,
    body: QuotePreviewIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuotePreviewOut:
    overrides: dict[uuid.UUID, int] = {}
    for k, v in body.line_overrides.items():
        try:
            overrides[uuid.UUID(str(k))] = int(v)
        except (ValueError, TypeError):
            continue
    amount_overrides = {str(k): int(v) for k, v in body.amount_overrides.items()}

    if body.draft:
        scale, lines, needs_pv = preview_quote_draft(
            db,
            fee_scale_id,
            body.draft,
            property_value_pence=body.property_value_pence,
            amount_overrides=amount_overrides,
        )
        computed_by_key: dict[str, object] = {}
        idx = 0
        for cat in sorted(body.draft, key=lambda c: (c.sort_order, c.key)):
            for dline in sorted(cat.lines, key=lambda ln: (ln.sort_order, ln.key)):
                if idx < len(lines):
                    computed_by_key[dline.key] = lines[idx]
                    idx += 1
        categories_out: list[QuotePreviewCategoryOut] = []
        flat_lines: list[QuotePreviewLineOut] = []
        for cat in sorted(body.draft, key=lambda c: (c.sort_order, c.key)):
            cat_lines: list[QuotePreviewLineOut] = []
            for dline in sorted(cat.lines, key=lambda ln: (ln.sort_order, ln.key)):
                computed = computed_by_key.get(dline.key)
                if computed is None:
                    continue
                row = _line_out_from_computed(dline.key, dline, computed)
                cat_lines.append(row)
                flat_lines.append(row)
            categories_out.append(
                QuotePreviewCategoryOut(
                    key=cat.key,
                    category_id=cat.category_id,
                    name=cat.name,
                    sort_order=cat.sort_order,
                    lines=cat_lines,
                )
            )
        return QuotePreviewOut(
            fee_scale_id=scale.id,
            property_value_pence=body.property_value_pence,
            needs_property_value=needs_pv,
            lines=flat_lines,
            categories=categories_out,
        )

    scale, lines, needs_pv = preview_quote_lines(
        db,
        fee_scale_id,
        property_value_pence=body.property_value_pence,
        overrides=overrides,
    )
    flat = [_preview_line_out(ln) for ln in lines]
    return QuotePreviewOut(
        fee_scale_id=scale.id,
        property_value_pence=body.property_value_pence,
        needs_property_value=needs_pv,
        lines=flat,
        categories=[],
    )


# ── Categories ────────────────────────────────────────────────────────────────

@router.post("/categories", response_model=FeeScaleCategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(payload: FeeScaleCategoryCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.get(FeeScale, payload.fee_scale_id) is None:
        raise HTTPException(status_code=404, detail="Fee scale not found")
    now = datetime.utcnow()
    row = FeeScaleCategory(
        id=uuid.uuid4(),
        fee_scale_id=payload.fee_scale_id,
        name=payload.name.strip(),
        sort_order=payload.sort_order,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return FeeScaleCategoryOut(id=row.id, fee_scale_id=row.fee_scale_id, name=row.name, sort_order=row.sort_order, lines=[])


@router.patch("/categories/{category_id}", response_model=FeeScaleCategoryOut)
def update_category(
    category_id: uuid.UUID,
    payload: FeeScaleCategoryUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(FeeScaleCategory, category_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Category not found")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        row.name = data["name"].strip()
    if "sort_order" in data and data["sort_order"] is not None:
        row.sort_order = data["sort_order"]
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    lines = db.execute(select(FeeScaleLine).where(FeeScaleLine.category_id == row.id)).scalars().all()
    return FeeScaleCategoryOut(
        id=row.id,
        fee_scale_id=row.fee_scale_id,
        name=row.name,
        sort_order=row.sort_order,
        lines=[_line_out(ln) for ln in lines],
    )


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(FeeScaleCategory, category_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Category not found")
    db.delete(row)
    db.commit()


# ── Lines ─────────────────────────────────────────────────────────────────────

@router.post("/lines", response_model=FeeScaleLineOut, status_code=status.HTTP_201_CREATED)
def create_line(payload: FeeScaleLineCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.get(FeeScaleCategory, payload.category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found")
    now = datetime.utcnow()
    row = FeeScaleLine(
        id=uuid.uuid4(),
        category_id=payload.category_id,
        name=payload.name.strip(),
        line_kind=FeeScaleLineKind(payload.line_kind),
        amount_kind=FeeScaleAmountKind(payload.amount_kind) if payload.amount_kind else None,
        default_amount_pence=payload.default_amount_pence,
        band_set_id=payload.band_set_id,
        vat_treatment=FeeScaleVatTreatment(payload.vat_treatment),
        sort_order=payload.sort_order,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _line_out(row)


@router.patch("/lines/{line_id}", response_model=FeeScaleLineOut)
def update_line(
    line_id: uuid.UUID,
    payload: FeeScaleLineUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(FeeScaleLine, line_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Line not found")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        row.name = data["name"].strip()
    if "line_kind" in data and data["line_kind"] is not None:
        row.line_kind = FeeScaleLineKind(data["line_kind"])
    if "amount_kind" in data:
        row.amount_kind = FeeScaleAmountKind(data["amount_kind"]) if data["amount_kind"] else None
    if "default_amount_pence" in data:
        row.default_amount_pence = data["default_amount_pence"]
    if "band_set_id" in data:
        row.band_set_id = data["band_set_id"]
    if "vat_treatment" in data and data["vat_treatment"] is not None:
        from app.models import FeeScaleVatTreatment

        row.vat_treatment = FeeScaleVatTreatment(data["vat_treatment"])
    if "sort_order" in data and data["sort_order"] is not None:
        row.sort_order = data["sort_order"]
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _line_out(row)


@router.delete("/lines/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_line(line_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(FeeScaleLine, line_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Line not found")
    db.delete(row)
    db.commit()


# ── Band sets ─────────────────────────────────────────────────────────────────

@router.post("/band-sets", response_model=FeeScaleBandSetOut, status_code=status.HTTP_201_CREATED)
def create_band_set(payload: FeeScaleBandSetCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.get(FeeScale, payload.fee_scale_id) is None:
        raise HTTPException(status_code=404, detail="Fee scale not found")
    now = datetime.utcnow()
    row = FeeScaleBandSet(
        id=uuid.uuid4(),
        fee_scale_id=payload.fee_scale_id,
        name=payload.name.strip(),
        sort_order=payload.sort_order,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return FeeScaleBandSetOut(id=row.id, fee_scale_id=row.fee_scale_id, name=row.name, sort_order=row.sort_order, rows=[])


@router.patch("/band-sets/{band_set_id}", response_model=FeeScaleBandSetOut)
def update_band_set(
    band_set_id: uuid.UUID,
    payload: FeeScaleBandSetUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(FeeScaleBandSet, band_set_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Band set not found")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        row.name = data["name"].strip()
    if "sort_order" in data and data["sort_order"] is not None:
        row.sort_order = data["sort_order"]
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    rows = db.execute(select(FeeScaleBandRow).where(FeeScaleBandRow.band_set_id == row.id)).scalars().all()
    return FeeScaleBandSetOut(
        id=row.id,
        fee_scale_id=row.fee_scale_id,
        name=row.name,
        sort_order=row.sort_order,
        rows=[
            FeeScaleBandRowOut(
                id=r.id,
                band_set_id=r.band_set_id,
                min_value_pence=int(r.min_value_pence),
                max_value_pence=int(r.max_value_pence) if r.max_value_pence is not None else None,
                amount_pence=r.amount_pence,
                sort_order=r.sort_order,
            )
            for r in rows
        ],
    )


@router.delete("/band-sets/{band_set_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_band_set(band_set_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(FeeScaleBandSet, band_set_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Band set not found")
    db.delete(row)
    db.commit()


@router.post("/band-rows", response_model=FeeScaleBandRowOut, status_code=status.HTTP_201_CREATED)
def create_band_row(payload: FeeScaleBandRowCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.get(FeeScaleBandSet, payload.band_set_id) is None:
        raise HTTPException(status_code=404, detail="Band set not found")
    now = datetime.utcnow()
    row = FeeScaleBandRow(
        id=uuid.uuid4(),
        band_set_id=payload.band_set_id,
        min_value_pence=payload.min_value_pence,
        max_value_pence=payload.max_value_pence,
        amount_pence=payload.amount_pence,
        sort_order=payload.sort_order,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return FeeScaleBandRowOut(
        id=row.id,
        band_set_id=row.band_set_id,
        min_value_pence=int(row.min_value_pence),
        max_value_pence=int(row.max_value_pence) if row.max_value_pence is not None else None,
        amount_pence=row.amount_pence,
        sort_order=row.sort_order,
    )


@router.patch("/band-rows/{row_id}", response_model=FeeScaleBandRowOut)
def update_band_row(
    row_id: uuid.UUID,
    payload: FeeScaleBandRowUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(FeeScaleBandRow, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Band row not found")
    data = payload.model_dump(exclude_unset=True)
    if "min_value_pence" in data and data["min_value_pence"] is not None:
        row.min_value_pence = data["min_value_pence"]
    if "max_value_pence" in data:
        row.max_value_pence = data["max_value_pence"]
    if "amount_pence" in data and data["amount_pence"] is not None:
        row.amount_pence = data["amount_pence"]
    if "sort_order" in data and data["sort_order"] is not None:
        row.sort_order = data["sort_order"]
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return FeeScaleBandRowOut(
        id=row.id,
        band_set_id=row.band_set_id,
        min_value_pence=int(row.min_value_pence),
        max_value_pence=int(row.max_value_pence) if row.max_value_pence is not None else None,
        amount_pence=row.amount_pence,
        sort_order=row.sort_order,
    )


@router.delete("/band-rows/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_band_row(row_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(FeeScaleBandRow, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Band row not found")
    db.delete(row)
    db.commit()
