"""Unit tests for quote merge field generation."""

from app.compose_quote import _quote_line_merge_fields
from app.fee_scale_calc import ComputedQuoteLine
from app.models import FeeScaleLineKind


def test_quote_line_merge_fields_indexed() -> None:
    lines = [
        ComputedQuoteLine(
            line_id=None,
            name="Legal Fees on Sale",
            line_kind=FeeScaleLineKind.item,
            amount_pence=129000,
            vat_pence=25800,
            editable=True,
            is_bold=False,
            align_right=True,
        ),
        ComputedQuoteLine(
            line_id=None,
            name="TOTAL FEES (including VAT)",
            line_kind=FeeScaleLineKind.subtotal,
            amount_pence=129000,
            vat_pence=25800,
            editable=False,
            is_bold=True,
            align_right=True,
        ),
    ]
    fields = _quote_line_merge_fields(lines, property_value_pence=300_000_00)
    assert fields["[QUOTE_PROPERTY_VALUE]"] == "£300,000.00"
    assert fields["[QUOTE_01_LABEL]"] == "Legal Fees on Sale"
    assert fields["[QUOTE_01_AMOUNT]"] == "£1,290.00"
    assert fields["[QUOTE_01_VAT]"] == "£258.00"
    assert fields["[QUOTE_MAIN_TOTAL]"] == "£1,290.00"
    assert fields["[QUOTE_VAT_TOTAL]"] == "£258.00"
    assert fields["[QUOTE_GRAND_TOTAL]"] == "£1,548.00"
    assert fields["[QUOTE_02_LABEL]"] == "TOTAL FEES (including VAT)"
    assert fields["[QUOTE_02_AMOUNT]"] == "£1,290.00"
    assert fields["[QUOTE_02_VAT]"] == "£258.00"
    assert fields["[b:QUOTE_02_LABEL]"] == "TOTAL FEES (including VAT)"
    assert fields["[QUOTE_25_LABEL]"] == ""
    assert fields["[QUOTE_25_AMOUNT]"] == ""
    assert fields["[QUOTE_25_VAT]"] == ""
