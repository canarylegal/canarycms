"""Fee scale CRUD and quote preview loading."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fee_scale_calc import (
    ComputedQuoteLine,
    compute_quote_from_draft,
    compute_quote_lines,
    draft_needs_property_value,
    scale_needs_property_value,
)
from app.models import (
    FeeScale,
    FeeScaleAmountKind,
    FeeScaleBandRow,
    FeeScaleBandSet,
    FeeScaleCategory,
    FeeScaleLine,
    FeeScaleLineKind,
    MatterHeadType,
    MatterSubType,
)


def _ensure_reference_unique(db: Session, ref: str, *, exclude_id: uuid.UUID | None = None) -> str:
    q = select(FeeScale).where(FeeScale.reference == ref)
    if exclude_id is not None:
        q = q.where(FeeScale.id != exclude_id)
    if db.execute(q.limit(1)).scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reference already in use")
    return ref


def _validate_scope(db: Session, mh: uuid.UUID | None, ms: uuid.UUID | None) -> None:
    if ms is not None and mh is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Matter type required when sub-type is set")
    if mh is not None:
        if db.get(MatterHeadType, mh) is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Matter type not found")
    if ms is not None:
        sub = db.get(MatterSubType, ms)
        if sub is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Matter sub-type not found")
        if mh is not None and sub.head_type_id != mh:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sub-type does not belong to matter type")


def fee_scale_matches_case(
    scale: FeeScale,
    *,
    matter_head_type_id: uuid.UUID | None,
    matter_sub_type_id: uuid.UUID | None,
) -> bool:
    if scale.matter_head_type_id is None and scale.matter_sub_type_id is None:
        return True
    if scale.matter_sub_type_id is not None:
        return scale.matter_sub_type_id == matter_sub_type_id
    return scale.matter_head_type_id == matter_head_type_id


def load_scale_graph(db: Session, scale_id: uuid.UUID) -> tuple[
    FeeScale,
    list[FeeScaleCategory],
    dict[uuid.UUID, list[FeeScaleLine]],
    list[FeeScaleBandSet],
    dict[uuid.UUID, list[FeeScaleBandRow]],
]:
    scale = db.get(FeeScale, scale_id)
    if scale is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fee scale not found")
    categories = (
        db.execute(
            select(FeeScaleCategory)
            .where(FeeScaleCategory.fee_scale_id == scale_id)
            .order_by(FeeScaleCategory.sort_order, FeeScaleCategory.created_at)
        )
        .scalars()
        .all()
    )
    cat_ids = [c.id for c in categories]
    lines_by_cat: dict[uuid.UUID, list[FeeScaleLine]] = {cid: [] for cid in cat_ids}
    all_lines: list[FeeScaleLine] = []
    if cat_ids:
        for ln in (
            db.execute(
                select(FeeScaleLine)
                .where(FeeScaleLine.category_id.in_(cat_ids))
                .order_by(FeeScaleLine.sort_order, FeeScaleLine.created_at)
            )
            .scalars()
            .all()
        ):
            lines_by_cat[ln.category_id].append(ln)
            all_lines.append(ln)
    band_sets = (
        db.execute(
            select(FeeScaleBandSet)
            .where(FeeScaleBandSet.fee_scale_id == scale_id)
            .order_by(FeeScaleBandSet.sort_order, FeeScaleBandSet.created_at)
        )
        .scalars()
        .all()
    )
    set_ids = [s.id for s in band_sets]
    rows_by_set: dict[uuid.UUID, list[FeeScaleBandRow]] = {sid: [] for sid in set_ids}
    if set_ids:
        for row in (
            db.execute(
                select(FeeScaleBandRow)
                .where(FeeScaleBandRow.band_set_id.in_(set_ids))
                .order_by(FeeScaleBandRow.sort_order, FeeScaleBandRow.min_value_pence)
            )
            .scalars()
            .all()
        ):
            rows_by_set[row.band_set_id].append(row)
    return scale, list(categories), lines_by_cat, list(band_sets), rows_by_set


def preview_quote_lines(
    db: Session,
    scale_id: uuid.UUID,
    *,
    property_value_pence: int | None,
    overrides: dict[uuid.UUID, int] | None,
) -> tuple[FeeScale, list[ComputedQuoteLine], bool]:
    scale, categories, lines_by_cat, _sets, rows_by_set = load_scale_graph(db, scale_id)
    all_lines = [ln for lines in lines_by_cat.values() for ln in lines]
    needs_pv = scale_needs_property_value(all_lines)
    lines = compute_quote_lines(
        scale,
        categories,
        lines_by_cat,
        rows_by_set,
        property_value_pence=property_value_pence,
        overrides=overrides,
    )
    return scale, lines, needs_pv


def preview_quote_draft(
    db: Session,
    scale_id: uuid.UUID,
    draft_categories: list,
    *,
    property_value_pence: int | None,
    amount_overrides: dict[str, int] | None,
) -> tuple[FeeScale, list[ComputedQuoteLine], bool]:
    scale, _categories, _lines_by_cat, _sets, rows_by_set = load_scale_graph(db, scale_id)
    needs_pv = draft_needs_property_value(draft_categories)
    lines = compute_quote_from_draft(
        scale,
        draft_categories,
        rows_by_set,
        property_value_pence=property_value_pence,
        amount_overrides=amount_overrides,
    )
    return scale, lines, needs_pv
