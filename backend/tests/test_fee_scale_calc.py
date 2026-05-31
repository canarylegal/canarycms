"""Fee scale quote calculation."""

import uuid

from app.fee_scale_calc import compute_quote_lines
from app.models import FeeScale, FeeScaleAmountKind, FeeScaleCategory, FeeScaleLine, FeeScaleLineKind


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


def test_vat_and_subtotal() -> None:
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
            include_in_vat=True,
            sort_order=0,
        ),
        FeeScaleLine(
            id=uuid.uuid4(),
            category_id=cat_id,
            name="TT fee",
            line_kind=FeeScaleLineKind.item,
            amount_kind=FeeScaleAmountKind.fixed,
            default_amount_pence=3500,
            include_in_vat=False,
            sort_order=1,
        ),
        FeeScaleLine(
            id=uuid.uuid4(),
            category_id=cat_id,
            name="VAT",
            line_kind=FeeScaleLineKind.vat,
            sort_order=2,
        ),
        FeeScaleLine(
            id=uuid.uuid4(),
            category_id=cat_id,
            name="Total fees",
            line_kind=FeeScaleLineKind.subtotal,
            sort_order=3,
        ),
    ]
    out = compute_quote_lines(_scale(), [cat], {cat_id: lines}, {}, property_value_pence=None)
    amounts = {ln.name: ln.amount_pence for ln in out}
    assert amounts["Legal fee"] == 100000
    assert amounts["VAT"] == 20000  # 20% of 100000 only
from app.fee_scale_calc import compute_quote_from_draft
from app.models import FeeScale, FeeScaleAmountKind, FeeScaleLineKind


class _DraftLine:
    def __init__(
        self,
        *,
        key: str,
        name: str,
        line_kind: str,
        amount_kind: str | None = None,
        amount_pence: int | None = None,
        include_in_vat: bool = False,
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
        self.include_in_vat = include_in_vat
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
                include_in_vat=True,
                sort_order=0,
            ),
            _DraftLine(key="l2", name="VAT", line_kind=FeeScaleLineKind.vat.value, sort_order=1),
            _DraftLine(key="l3", name="Total", line_kind=FeeScaleLineKind.subtotal.value, sort_order=2),
        ],
    )
    out = compute_quote_from_draft(_scale(), [cat], {}, property_value_pence=None, amount_overrides={"l1": 110000})
    amounts = {ln.name: ln.amount_pence for ln in out}
    assert amounts["Legal fee"] == 110000
    assert amounts["VAT"] == 22000
    assert amounts["Total"] == 132000
