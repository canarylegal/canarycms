from datetime import date

from app.docx_util import invoice_line_merge_fields


def test_invoice_line_merge_fields_formats_amounts() -> None:
    fields = invoice_line_merge_fields(
        invoice_number="INV-1001",
        invoice_date=date(2026, 6, 13),
        bill_to_name="Jane Client",
        lines=[
            {
                "line_type": "fee",
                "description": "Legal fees",
                "amount_pence": 100000,
                "tax_pence": 20000,
            },
            {
                "line_type": "disbursement",
                "description": "Search fee",
                "amount_pence": 5000,
                "tax_pence": 0,
            },
        ],
        total_pence=125000,
    )
    assert fields["[INVOICE_NUMBER]"] == "INV-1001"
    assert fields["[INVOICE_DATE]"] == "13 June 2026"
    assert fields["[INVOICE_BILL_TO]"] == "Jane Client"
    assert fields["[INVOICE_01_TYPE]"] == "Fee"
    assert fields["[INVOICE_01_DESCRIPTION]"] == "Legal fees"
    assert fields["[INVOICE_01_NET]"] == "£1,000.00"
    assert fields["[INVOICE_01_VAT]"] == "£200.00"
    assert fields["[INVOICE_01_TOTAL]"] == "£1,200.00"
    assert fields["[INVOICE_02_TYPE]"] == "Disbursement"
    assert fields["[INVOICE_NET_TOTAL]"] == "£1,050.00"
    assert fields["[INVOICE_VAT_TOTAL]"] == "£200.00"
    assert fields["[INVOICE_TOTAL]"] == "£1,250.00"
    assert fields["[INVOICE_03_TYPE]"] == ""
