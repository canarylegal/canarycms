"""Quote → finance VAT conversion."""

from app.finance_service import _quote_amounts_by_name, _quote_finance_rows
from app.models import FeeScaleLineKind


def test_quote_finance_rows_reads_vat_from_amount_pence_on_vat_lines() -> None:
    quote_lines = [
        {"name": "Legal fee", "line_kind": FeeScaleLineKind.item.value, "amount_pence": 100_000},
        {"name": "VAT", "line_kind": FeeScaleLineKind.vat.value, "amount_pence": 20_000},
    ]
    rows = _quote_finance_rows(quote_lines)
    assert rows == [("", "Legal fee", 100_000, None), ("", "VAT", 20_000, None)]


def test_quote_finance_rows_includes_plus_vat_items_and_vat_summary_lines() -> None:
    quote_lines = [
        {"name": "Fees", "line_kind": FeeScaleLineKind.section_header.value},
        {
            "name": "Legal fee",
            "line_kind": FeeScaleLineKind.item.value,
            "amount_pence": 100_000,
            "vat_pence": 20_000,
        },
        {
            "name": "VAT",
            "line_kind": FeeScaleLineKind.vat.value,
            "amount_pence": None,
            "vat_pence": 20_000,
        },
    ]
    rows = _quote_finance_rows(quote_lines)
    assert rows == [("Fees", "Legal fee", 100_000, 20_000)]


def test_quote_finance_rows_uses_vat_summary_when_items_have_no_vat() -> None:
    quote_lines = [
        {"name": "Fees", "line_kind": FeeScaleLineKind.section_header.value},
        {
            "name": "Legal fee",
            "line_kind": FeeScaleLineKind.item.value,
            "amount_pence": 100_000,
            "vat_pence": None,
        },
        {
            "name": "VAT",
            "line_kind": FeeScaleLineKind.vat.value,
            "amount_pence": None,
            "vat_pence": 20_000,
        },
    ]
    rows = _quote_finance_rows(quote_lines)
    assert rows == [
        ("Fees", "Legal fee", 100_000, None),
        ("Fees", "VAT", 20_000, None),
    ]
    amounts = _quote_amounts_by_name(quote_lines)
    assert amounts["legal fee"] == (100_000, None)
    assert amounts["vat"] == (20_000, None)


def test_quote_finance_rows_skips_aggregate_vat_when_items_have_per_line_vat() -> None:
    """After fee-scale enrichment, per-line VAT replaces the quote VAT summary row."""
    quote_lines = [
        {
            "name": "Telegraphic Transfer Fee (each)",
            "line_kind": FeeScaleLineKind.item.value,
            "amount_pence": 3500,
            "vat_pence": 700,
        },
        {
            "name": "SDLT/LTT Submission Fee",
            "line_kind": FeeScaleLineKind.item.value,
            "amount_pence": 5000,
            "vat_pence": 1000,
        },
        {
            "name": "VAT",
            "line_kind": FeeScaleLineKind.vat.value,
            "amount_pence": None,
            "vat_pence": 3700,
        },
    ]
    rows = _quote_finance_rows(quote_lines)
    assert rows == [
        ("", "Telegraphic Transfer Fee (each)", 3500, 700),
        ("", "SDLT/LTT Submission Fee", 5000, 1000),
    ]
    assert "vat" not in _quote_amounts_by_name(quote_lines)
