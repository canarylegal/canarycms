"""Fee scale quote calculation."""

import uuid

from app.fee_scale_calc import compute_quote_from_draft, compute_quote_lines, quote_column_totals
from app.models import (
    FeeScale,
    FeeScaleAmountKind,
    FeeScaleCategory,
    FeeScaleLine,
    FeeScaleLineKind,
    FeeScaleVatTreatment,
)


def _scale() -> FeeScale:
    return FeeScale(
        id=uuid.uuid4(),
        name="Test",
        reference="t1",
        vat_rate_bps=2000,
        matter_head_type_id=None,
        matter_sub_type_id=None,
        owner_id=uuid.uuid4(),
    )


def test_plus_vat_item_shows_vat_column() -> None:
    cat_id = uuid.uuid4()
    cat = FeeScaleCategory(id=cat_id, fee_scale_id=uuid.uuid4(), name="Fees", sort_order=0)
    lines = [
        FeeScaleLine(
            id=uuid.uuid4(),
            category_id=cat_id,
            name="Legal fee",
            line_kind=FeeScaleLineKind.item,
            amount_kind=FeeScaleAmountKind.fixed,
            default_amount_pence=100000,
            vat_treatment=FeeScaleVatTreatment.plus_vat,
            sort_order=0,
        ),
        FeeScaleLine(
            id=uuid.uuid4(),
            category_id=cat_id,
            name="TT fee",
            line_kind=FeeScaleLineKind.item,
            amount_kind=FeeScaleAmountKind.fixed,
            default_amount_pence=3500,
            vat_treatment=FeeScaleVatTreatment.included,
            sort_order=1,
        ),
    ]
    out = compute_quote_lines(_scale(), [cat], {cat_id: lines}, {}, property_value_pence=None)
    by_name = {ln.name: ln for ln in out}
    assert by_name["Legal fee"].amount_pence == 100000
    assert by_name["Legal fee"].vat_pence == 20000
    assert by_name["TT fee"].vat_pence is None
    main, vat = quote_column_totals(out)
    assert main == 103500
    assert vat == 20000


def test_legacy_vat_line_kind() -> None:
    cat_id = uuid.uuid4()
    cat = FeeScaleCategory(id=cat_id, fee_scale_id=uuid.uuid4(), name="Fees", sort_order=0)
    lines = [
        FeeScaleLine(
            id=uuid.uuid4(),
            category_id=cat_id,
            name="Legal fee",
            line_kind=FeeScaleLineKind.item,
            amount_kind=FeeScaleAmountKind.fixed,
            default_amount_pence=100000,
            vat_treatment=FeeScaleVatTreatment.plus_vat,
            sort_order=0,
        ),
        FeeScaleLine(
            id=uuid.uuid4(),
            category_id=cat_id,
            name="VAT",
            line_kind=FeeScaleLineKind.vat,
            vat_treatment=FeeScaleVatTreatment.included,
            sort_order=1,
        ),
        FeeScaleLine(
            id=uuid.uuid4(),
            category_id=cat_id,
            name="Total fees",
            line_kind=FeeScaleLineKind.subtotal,
            vat_treatment=FeeScaleVatTreatment.included,
            sort_order=2,
        ),
    ]
    out = compute_quote_lines(_scale(), [cat], {cat_id: lines}, {}, property_value_pence=None)
    amounts = {ln.name: (ln.amount_pence, ln.vat_pence) for ln in out}
    assert amounts["Legal fee"] == (100000, 20000)
    assert amounts["VAT"] == (None, 20000)
    assert amounts["Total fees"] == (100000, 20000)  # main + rolled-up VAT column


class _DraftLine:
    def __init__(
        self,
        *,
        key: str,
        name: str,
        line_kind: str,
        amount_kind: str | None = None,
        amount_pence: int | None = None,
        vat_treatment: str = "included",
        band_set_id=None,
        sort_order: int = 0,
        line_id=None,
    ):
        self.key = key
        self.line_id = line_id
        self.name = name
        self.line_kind = line_kind
        self.amount_kind = amount_kind
        self.amount_pence = amount_pence
        self.vat_treatment = vat_treatment
        self.band_set_id = band_set_id
        self.sort_order = sort_order


class _DraftCat:
    def __init__(self, *, key: str, name: str, sort_order: int, lines: list[_DraftLine]):
        self.key = key
        self.name = name
        self.sort_order = sort_order
        self.lines = lines


def test_compute_quote_from_draft_respects_overrides() -> None:
    cat = _DraftCat(
        key="c1",
        name="Fees",
        sort_order=0,
        lines=[
            _DraftLine(
                key="l1",
                name="Legal fee",
                line_kind=FeeScaleLineKind.item.value,
                amount_kind=FeeScaleAmountKind.fixed.value,
                amount_pence=100000,
                vat_treatment="plus_vat",
                sort_order=0,
            ),
            _DraftLine(key="l2", name="VAT", line_kind=FeeScaleLineKind.vat.value, sort_order=1),
            _DraftLine(key="l3", name="Total", line_kind=FeeScaleLineKind.subtotal.value, sort_order=2),
        ],
    )
    out = compute_quote_from_draft(_scale(), [cat], {}, property_value_pence=None, amount_overrides={"l1": 110000})
    amounts = {ln.name: ln.amount_pence for ln in out}
    vats = {ln.name: ln.vat_pence for ln in out}
    assert amounts["Legal fee"] == 110000
    assert vats["Legal fee"] == 22000
    assert amounts["Total"] == 110000
