from datetime import date

from app.docx_util import completion_line_merge_fields


def test_completion_line_merge_fields_formats_rows_and_balance() -> None:
    class Item:
        def __init__(
            self,
            name: str,
            direction: str,
            amount_pence: int | None,
            vat_pence: int | None = None,
        ):
            self.name = name
            self.direction = direction
            self.amount_pence = amount_pence
            self.vat_pence = vat_pence

    class Category:
        def __init__(self, name: str, items: list[Item]):
            self.name = name
            self.items = items

    class Finance:
        def __init__(self) -> None:
            self.categories = [
                Category("Purchase price", [Item("Amount due", "credit", 200_000_00)]),
                Category(
                    "Costs",
                    [Item("Legal fees", "debit", 1_500_00, 300_00)],
                ),
            ]

    fields = completion_line_merge_fields(statement_date=date(2026, 6, 14), finance=Finance())
    assert fields["[COMPLETION_DATE]"] == "14 June 2026"
    assert fields["[COMPLETION_01_DESCRIPTION]"] == "PURCHASE PRICE"
    assert fields["[COMPLETION_02_DESCRIPTION]"] == "Amount due"
    assert fields["[COMPLETION_02_CREDIT]"] == "£200,000.00"
    assert fields["[COMPLETION_03_DESCRIPTION]"] == "COSTS"
    assert fields["[COMPLETION_04_DESCRIPTION]"] == "Legal fees"
    assert fields["[COMPLETION_04_DEBIT]"] == "£1,500.00"
    assert fields["[COMPLETION_05_DESCRIPTION]"] == "VAT on Legal fees"
    assert fields["[COMPLETION_05_DEBIT]"] == "£300.00"
    assert fields["[COMPLETION_BALANCE_LABEL]"] == "BALANCE DUE FROM CLIENT"
    assert fields["[COMPLETION_BALANCE_AMOUNT]"] == "£198,200.00"
