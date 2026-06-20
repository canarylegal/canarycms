"""Quote compose uses built-in template (not blank letter) when no quote letterhead."""

import io
import zipfile

from app.docx_util import write_quote_template_docx_bytes
def test_builtin_quote_template_has_fee_table_slots() -> None:
    raw = write_quote_template_docx_bytes(slots=3)
    xml = zipfile.ZipFile(io.BytesIO(raw)).read("word/document.xml").decode()
    assert "[QUOTE_01_LABEL]" in xml
    assert "[QUOTE_03_VAT]" in xml
    assert "[PRECEDENT_BODY]" not in xml


def test_load_quote_template_without_letterhead_uses_builtin() -> None:
    raw = write_quote_template_docx_bytes()
    xml = zipfile.ZipFile(io.BytesIO(raw)).read("word/document.xml").decode()
    assert "[QUOTE_01_LABEL]" in xml
    assert "[QUOTE_01_AMOUNT]" in xml


def test_builtin_quote_template_merges_fee_lines() -> None:
    from app.docx_util import apply_quote_table_presentation, merge_precedent_codes, strip_empty_quote_table_rows
    from app.compose_quote import _quote_line_merge_fields
    from app.models import FeeScaleLineKind
    from app.fee_scale_calc import ComputedQuoteLine

    raw = write_quote_template_docx_bytes(slots=5)
    lines = [
        ComputedQuoteLine(
            line_id=None,
            name="Legal fee",
            line_kind=FeeScaleLineKind.item,
            amount_pence=92500,
            vat_pence=18500,
            editable=False,
            is_bold=False,
            align_right=True,
        ),
    ]
    fields = _quote_line_merge_fields(lines, property_value_pence=15000000)
    merged = merge_precedent_codes(raw, fields)
    cleaned = strip_empty_quote_table_rows(merged)
    styled = apply_quote_table_presentation(cleaned, lines)
    xml = zipfile.ZipFile(io.BytesIO(styled)).read("word/document.xml").decode()
    assert "Legal fee" in xml
    assert "925.00" in xml
    assert "QUOTE_01_LABEL" not in xml
    assert 'w:fill="D0DAEA"' in xml


def test_apply_quote_table_presentation_styles_section_and_total_rows() -> None:
    from app.docx_util import apply_quote_table_presentation, merge_precedent_codes, strip_empty_quote_table_rows
    from app.compose_quote import _quote_line_merge_fields
    from app.models import FeeScaleLineKind
    from app.fee_scale_calc import ComputedQuoteLine

    raw = write_quote_template_docx_bytes(slots=8)
    lines = [
        ComputedQuoteLine(
            line_id=None,
            name="Disbursements/Fees paid to Third Parties",
            line_kind=FeeScaleLineKind.section_header,
            amount_pence=None,
            editable=False,
            is_bold=True,
            align_right=False,
        ),
        ComputedQuoteLine(
            line_id=None,
            name="Telegraphic Transfer Fee",
            line_kind=FeeScaleLineKind.item,
            amount_pence=4000,
            vat_pence=None,
            editable=False,
            is_bold=False,
            align_right=True,
        ),
        ComputedQuoteLine(
            line_id=None,
            name="TOTAL DISBURSEMENTS",
            line_kind=FeeScaleLineKind.subtotal,
            amount_pence=4000,
            vat_pence=None,
            editable=False,
            is_bold=True,
            align_right=True,
        ),
    ]
    fields = _quote_line_merge_fields(lines, property_value_pence=None)
    merged = merge_precedent_codes(raw, fields)
    cleaned = strip_empty_quote_table_rows(merged)
    styled = apply_quote_table_presentation(cleaned, lines)
    xml = zipfile.ZipFile(io.BytesIO(styled)).read("word/document.xml").decode()
    assert "Disbursements/Fees paid to Third Parties" in xml
    assert 'w:fill="EEF2F8"' in xml
    assert "TOTAL DISBURSEMENTS" in xml
