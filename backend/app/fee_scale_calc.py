"""Calculate quote line amounts from a native fee scale definition."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from app.models import (
    FeeScale,
    FeeScaleAmountKind,
    FeeScaleBandRow,
    FeeScaleCategory,
    FeeScaleLine,
    FeeScaleLineKind,
)


class DraftLineLike(Protocol):
    key: str
    line_id: uuid.UUID | None
    name: str
    line_kind: str
    amount_kind: str | None
    amount_pence: int | None
    include_in_vat: bool
    band_set_id: uuid.UUID | None
    sort_order: int


class DraftCategoryLike(Protocol):
    key: str
    name: str
    sort_order: int
    lines: list[DraftLineLike]


@dataclass
class ComputedQuoteLine:
    line_id: uuid.UUID | None
    name: str
    line_kind: FeeScaleLineKind
    amount_pence: int | None
    editable: bool
    is_bold: bool
    align_right: bool


def _band_lookup(rows: list[FeeScaleBandRow], property_value_pence: int) -> int | None:
    ordered = sorted(rows, key=lambda r: (r.sort_order, r.min_value_pence))
    for row in ordered:
        if property_value_pence < row.min_value_pence:
            continue
        if row.max_value_pence is not None and property_value_pence > row.max_value_pence:
            continue
        return row.amount_pence
    return None


def _item_amount(
    line: FeeScaleLine,
    *,
    property_value_pence: int | None,
    overrides: dict[uuid.UUID, int],
    band_rows_by_set: dict[uuid.UUID, list[FeeScaleBandRow]],
) -> int | None:
    if line.id in overrides:
        return overrides[line.id]
    kind = line.amount_kind
    if kind == FeeScaleAmountKind.fixed:
        return line.default_amount_pence
    if kind == FeeScaleAmountKind.editable:
        return line.default_amount_pence
    if kind == FeeScaleAmountKind.band:
        if line.band_set_id is None or property_value_pence is None:
            return line.default_amount_pence
        rows = band_rows_by_set.get(line.band_set_id, [])
        found = _band_lookup(rows, property_value_pence)
        return found if found is not None else line.default_amount_pence
    return line.default_amount_pence


def compute_quote_lines(
    scale: FeeScale,
    categories: list[FeeScaleCategory],
    lines_by_category: dict[uuid.UUID, list[FeeScaleLine]],
    band_rows_by_set: dict[uuid.UUID, list[FeeScaleBandRow]],
    *,
    property_value_pence: int | None,
    overrides: dict[uuid.UUID, int] | None = None,
) -> list[ComputedQuoteLine]:
    """Walk categories/lines in order and produce display rows with calculated amounts."""
    overrides = overrides or {}
    out: list[ComputedQuoteLine] = []
    subtotal_results: list[int] = []
    section_amounts: list[int] = []
    section_vatable: list[int] = []

    def flush_section() -> None:
        nonlocal section_amounts, section_vatable
        section_amounts = []
        section_vatable = []

    for cat in sorted(categories, key=lambda c: (c.sort_order, c.created_at)):
        lines = sorted(lines_by_category.get(cat.id, []), key=lambda ln: (ln.sort_order, ln.created_at))
        if not lines and cat.name.strip():
            out.append(
                ComputedQuoteLine(
                    line_id=None,
                    name=cat.name,
                    line_kind=FeeScaleLineKind.section_header,
                    amount_pence=None,
                    editable=False,
                    is_bold=True,
                    align_right=False,
                )
            )
        for line in lines:
            if line.line_kind == FeeScaleLineKind.section_header:
                flush_section()
                out.append(
                    ComputedQuoteLine(
                        line_id=line.id,
                        name=line.name,
                        line_kind=line.line_kind,
                        amount_pence=None,
                        editable=False,
                        is_bold=True,
                        align_right=False,
                    )
                )
                continue

            if line.line_kind == FeeScaleLineKind.item:
                amount = _item_amount(
                    line,
                    property_value_pence=property_value_pence,
                    overrides=overrides,
                    band_rows_by_set=band_rows_by_set,
                )
                editable = True
                out.append(
                    ComputedQuoteLine(
                        line_id=line.id,
                        name=line.name,
                        line_kind=line.line_kind,
                        amount_pence=amount,
                        editable=editable,
                        is_bold=False,
                        align_right=True,
                    )
                )
                if amount is not None:
                    section_amounts.append(amount)
                    if line.include_in_vat:
                        section_vatable.append(amount)
                continue

            if line.line_kind == FeeScaleLineKind.vat:
                base = sum(section_vatable)
                vat = round(base * scale.vat_rate_bps / 10000)
                out.append(
                    ComputedQuoteLine(
                        line_id=line.id,
                        name=line.name,
                        line_kind=line.line_kind,
                        amount_pence=vat,
                        editable=False,
                        is_bold=False,
                        align_right=True,
                    )
                )
                section_amounts.append(vat)
                continue

            if line.line_kind == FeeScaleLineKind.subtotal:
                sub = sum(section_amounts)
                out.append(
                    ComputedQuoteLine(
                        line_id=line.id,
                        name=line.name,
                        line_kind=line.line_kind,
                        amount_pence=sub,
                        editable=False,
                        is_bold=True,
                        align_right=True,
                    )
                )
                subtotal_results.append(sub)
                flush_section()
                continue

            if line.line_kind == FeeScaleLineKind.total:
                items_after_last_sub = sum(section_amounts)
                grand = sum(subtotal_results) + items_after_last_sub
                out.append(
                    ComputedQuoteLine(
                        line_id=line.id,
                        name=line.name,
                        line_kind=line.line_kind,
                        amount_pence=grand,
                        editable=False,
                        is_bold=True,
                        align_right=True,
                    )
                )
                continue

    return out


def scale_needs_property_value(lines: list[FeeScaleLine]) -> bool:
    return any(ln.line_kind == FeeScaleLineKind.item and ln.amount_kind == FeeScaleAmountKind.band for ln in lines)


def draft_needs_property_value(categories: list[DraftCategoryLike]) -> bool:
    for cat in categories:
        for ln in cat.lines:
            if ln.line_kind == FeeScaleLineKind.item.value and ln.amount_kind == FeeScaleAmountKind.band.value:
                return True
    return False


def _draft_item_amount(
    line: DraftLineLike,
    *,
    property_value_pence: int | None,
    amount_overrides: dict[str, int],
    band_rows_by_set: dict[uuid.UUID, list[FeeScaleBandRow]],
) -> int | None:
    if line.key in amount_overrides:
        return amount_overrides[line.key]
    if line.line_id is not None and str(line.line_id) in amount_overrides:
        return amount_overrides[str(line.line_id)]
    kind = line.amount_kind
    if kind == FeeScaleAmountKind.band.value:
        if line.band_set_id is not None and property_value_pence is not None:
            rows = band_rows_by_set.get(line.band_set_id, [])
            found = _band_lookup(rows, property_value_pence)
            if found is not None:
                return found
        return line.amount_pence
    return line.amount_pence


def compute_quote_from_draft(
    scale: FeeScale,
    draft_categories: list[DraftCategoryLike],
    band_rows_by_set: dict[uuid.UUID, list[FeeScaleBandRow]],
    *,
    property_value_pence: int | None,
    amount_overrides: dict[str, int] | None = None,
) -> list[ComputedQuoteLine]:
    """Calculate quote lines from a user-editable draft (quote review step)."""
    amount_overrides = amount_overrides or {}
    out: list[ComputedQuoteLine] = []
    subtotal_results: list[int] = []
    section_amounts: list[int] = []
    section_vatable: list[int] = []

    def flush_section() -> None:
        nonlocal section_amounts, section_vatable
        section_amounts = []
        section_vatable = []

    for cat in sorted(draft_categories, key=lambda c: (c.sort_order, c.key)):
        lines = sorted(cat.lines, key=lambda ln: (ln.sort_order, ln.key))
        for line in lines:
            kind = FeeScaleLineKind(line.line_kind)

            if kind == FeeScaleLineKind.section_header:
                flush_section()
                out.append(
                    ComputedQuoteLine(
                        line_id=line.line_id,
                        name=line.name,
                        line_kind=kind,
                        amount_pence=None,
                        editable=False,
                        is_bold=True,
                        align_right=False,
                    )
                )
                continue

            if kind == FeeScaleLineKind.item:
                amount = _draft_item_amount(
                    line,
                    property_value_pence=property_value_pence,
                    amount_overrides=amount_overrides,
                    band_rows_by_set=band_rows_by_set,
                )
                editable = True
                out.append(
                    ComputedQuoteLine(
                        line_id=line.line_id,
                        name=line.name,
                        line_kind=kind,
                        amount_pence=amount,
                        editable=editable,
                        is_bold=False,
                        align_right=True,
                    )
                )
                if amount is not None:
                    section_amounts.append(amount)
                    if line.include_in_vat:
                        section_vatable.append(amount)
                continue

            if kind == FeeScaleLineKind.vat:
                base = sum(section_vatable)
                vat = round(base * scale.vat_rate_bps / 10000)
                out.append(
                    ComputedQuoteLine(
                        line_id=line.line_id,
                        name=line.name,
                        line_kind=kind,
                        amount_pence=vat,
                        editable=False,
                        is_bold=False,
                        align_right=True,
                    )
                )
                section_amounts.append(vat)
                continue

            if kind == FeeScaleLineKind.subtotal:
                sub = sum(section_amounts)
                out.append(
                    ComputedQuoteLine(
                        line_id=line.line_id,
                        name=line.name,
                        line_kind=kind,
                        amount_pence=sub,
                        editable=False,
                        is_bold=True,
                        align_right=True,
                    )
                )
                subtotal_results.append(sub)
                flush_section()
                continue

            if kind == FeeScaleLineKind.total:
                items_after_last_sub = sum(section_amounts)
                grand = sum(subtotal_results) + items_after_last_sub
                out.append(
                    ComputedQuoteLine(
                        line_id=line.line_id,
                        name=line.name,
                        line_kind=kind,
                        amount_pence=grand,
                        editable=False,
                        is_bold=True,
                        align_right=True,
                    )
                )
                continue

    return out
