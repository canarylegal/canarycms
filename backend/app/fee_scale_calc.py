"""Calculate quote line amounts from a native fee scale definition."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from app.fee_scale_vat import item_vat_pence, vat_pence_for_net
from app.models import (
    FeeScale,
    FeeScaleAmountKind,
    FeeScaleBandRow,
    FeeScaleCategory,
    FeeScaleLine,
    FeeScaleLineKind,
    FeeScaleVatTreatment,
)


class DraftLineLike(Protocol):
    key: str
    line_id: uuid.UUID | None
    name: str
    line_kind: str
    amount_kind: str | None
    amount_pence: int | None
    vat_treatment: str
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
    vat_pence: int | None = None
    vat_treatment: FeeScaleVatTreatment | None = None
    editable: bool = False
    is_bold: bool = False
    align_right: bool = False


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


def _parse_vat_treatment(raw: FeeScaleVatTreatment | str) -> FeeScaleVatTreatment:
    if isinstance(raw, FeeScaleVatTreatment):
        return raw
    try:
        return FeeScaleVatTreatment(str(raw))
    except ValueError:
        return FeeScaleVatTreatment.included


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
    subtotal_main: list[int] = []
    subtotal_vat: list[int] = []
    section_main: list[int] = []
    section_vat: list[int] = []
    section_vatable: list[int] = []

    def flush_section() -> None:
        nonlocal section_main, section_vat, section_vatable
        section_main = []
        section_vat = []
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
            continue
        if lines and cat.name.strip():
            first = lines[0]
            cat_name_norm = cat.name.strip().lower()
            first_is_same_header = (
                first.line_kind == FeeScaleLineKind.section_header
                and first.name.strip().lower() == cat_name_norm
            )
            if not first_is_same_header:
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
                treatment = line.vat_treatment
                vat = item_vat_pence(amount, treatment, scale.vat_rate_bps)
                out.append(
                    ComputedQuoteLine(
                        line_id=line.id,
                        name=line.name,
                        line_kind=line.line_kind,
                        amount_pence=amount,
                        vat_pence=vat,
                        vat_treatment=treatment,
                        editable=True,
                        is_bold=False,
                        align_right=True,
                    )
                )
                if amount is not None:
                    section_main.append(amount)
                    if vat is not None:
                        section_vat.append(vat)
                    if treatment == FeeScaleVatTreatment.plus_vat:
                        section_vatable.append(amount)
                continue

            if line.line_kind == FeeScaleLineKind.vat:
                base = sum(section_vatable)
                if base:
                    vat = vat_pence_for_net(base, scale.vat_rate_bps)
                    out.append(
                        ComputedQuoteLine(
                            line_id=line.id,
                            name=line.name,
                            line_kind=line.line_kind,
                            amount_pence=None,
                            vat_pence=vat,
                            editable=False,
                            is_bold=False,
                            align_right=True,
                        )
                    )
                    section_vat.append(vat)
                elif section_vat:
                    vat = sum(section_vat)
                    out.append(
                        ComputedQuoteLine(
                            line_id=line.id,
                            name=line.name,
                            line_kind=line.line_kind,
                            amount_pence=None,
                            vat_pence=vat,
                            editable=False,
                            is_bold=False,
                            align_right=True,
                        )
                    )
                continue

            if line.line_kind == FeeScaleLineKind.subtotal:
                sub_main = sum(section_main)
                sub_vat = sum(section_vat)
                out.append(
                    ComputedQuoteLine(
                        line_id=line.id,
                        name=line.name,
                        line_kind=line.line_kind,
                        amount_pence=sub_main,
                        vat_pence=sub_vat if sub_vat else None,
                        editable=False,
                        is_bold=True,
                        align_right=True,
                    )
                )
                subtotal_main.append(sub_main)
                subtotal_vat.append(sub_vat)
                flush_section()
                continue

            if line.line_kind == FeeScaleLineKind.total:
                items_main_after = sum(section_main)
                items_vat_after = sum(section_vat)
                grand_main = sum(subtotal_main) + items_main_after
                grand_vat = sum(subtotal_vat) + items_vat_after
                out.append(
                    ComputedQuoteLine(
                        line_id=line.id,
                        name=line.name,
                        line_kind=line.line_kind,
                        amount_pence=grand_main,
                        vat_pence=grand_vat if grand_vat else None,
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
    subtotal_main: list[int] = []
    subtotal_vat: list[int] = []
    section_main: list[int] = []
    section_vat: list[int] = []
    section_vatable: list[int] = []

    def flush_section() -> None:
        nonlocal section_main, section_vat, section_vatable
        section_main = []
        section_vat = []
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
                treatment = _parse_vat_treatment(line.vat_treatment)
                vat = item_vat_pence(amount, treatment, scale.vat_rate_bps)
                out.append(
                    ComputedQuoteLine(
                        line_id=line.line_id,
                        name=line.name,
                        line_kind=kind,
                        amount_pence=amount,
                        vat_pence=vat,
                        vat_treatment=treatment,
                        editable=True,
                        is_bold=False,
                        align_right=True,
                    )
                )
                if amount is not None:
                    section_main.append(amount)
                    if vat is not None:
                        section_vat.append(vat)
                    if treatment == FeeScaleVatTreatment.plus_vat:
                        section_vatable.append(amount)
                continue

            if kind == FeeScaleLineKind.vat:
                base = sum(section_vatable)
                if base:
                    vat = vat_pence_for_net(base, scale.vat_rate_bps)
                    out.append(
                        ComputedQuoteLine(
                            line_id=line.line_id,
                            name=line.name,
                            line_kind=kind,
                            amount_pence=None,
                            vat_pence=vat,
                            editable=False,
                            is_bold=False,
                            align_right=True,
                        )
                    )
                    section_vat.append(vat)
                elif section_vat:
                    vat = sum(section_vat)
                    out.append(
                        ComputedQuoteLine(
                            line_id=line.line_id,
                            name=line.name,
                            line_kind=kind,
                            amount_pence=None,
                            vat_pence=vat,
                            editable=False,
                            is_bold=False,
                            align_right=True,
                        )
                    )
                continue

            if kind == FeeScaleLineKind.subtotal:
                sub_main = sum(section_main)
                sub_vat = sum(section_vat)
                out.append(
                    ComputedQuoteLine(
                        line_id=line.line_id,
                        name=line.name,
                        line_kind=kind,
                        amount_pence=sub_main,
                        vat_pence=sub_vat if sub_vat else None,
                        editable=False,
                        is_bold=True,
                        align_right=True,
                    )
                )
                subtotal_main.append(sub_main)
                subtotal_vat.append(sub_vat)
                flush_section()
                continue

            if kind == FeeScaleLineKind.total:
                items_main_after = sum(section_main)
                items_vat_after = sum(section_vat)
                grand_main = sum(subtotal_main) + items_main_after
                grand_vat = sum(subtotal_vat) + items_vat_after
                out.append(
                    ComputedQuoteLine(
                        line_id=line.line_id,
                        name=line.name,
                        line_kind=kind,
                        amount_pence=grand_main,
                        vat_pence=grand_vat if grand_vat else None,
                        editable=False,
                        is_bold=True,
                        align_right=True,
                    )
                )
                continue

    return out


def quote_column_totals(lines: list[ComputedQuoteLine]) -> tuple[int, int]:
    """Return (main column total, VAT column total) from item lines only."""
    main = 0
    vat = 0
    for ln in lines:
        if ln.line_kind != FeeScaleLineKind.item:
            continue
        if ln.amount_pence is not None:
            main += ln.amount_pence
        if ln.vat_pence is not None:
            vat += ln.vat_pence
    return main, vat
