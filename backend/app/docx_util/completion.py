"""Completion statement merge fields and .docx writers."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from .proofing import _set_default_proofing_language_en_gb
from .quote_table import (
    COMPLETION_MERGE_SLOT_COUNT,
    _COMPLETION_SLOT_TOKEN_RE,
    format_gbp_pence,
)

def finance_item_completion_rows(item: Any) -> list[tuple[str, int, int]]:
    """Return completion-table rows as (description, debit_pence, credit_pence)."""
    name = (getattr(item, "name", None) or "").strip()
    direction = getattr(item, "direction", "debit")
    amount_pence = getattr(item, "amount_pence", None)
    vat_pence = getattr(item, "vat_pence", None)

    rows: list[tuple[str, int, int]] = []
    if direction == "credit":
        credit = int(amount_pence) if amount_pence else 0
        if name or credit:
            rows.append((name, 0, credit))
        return rows

    debit_net = int(amount_pence) if amount_pence else 0
    debit_vat = int(vat_pence) if vat_pence else 0
    if debit_net:
        rows.append((name, debit_net, 0))
    if debit_vat:
        vat_label = f"VAT on {name}" if debit_net else name
        rows.append((vat_label, debit_vat, 0))
    elif name and not debit_net and name.strip().lower() != "vat":
        rows.append((name, 0, 0))
    return rows


def completion_line_merge_fields(
    *,
    statement_date: date,
    finance: Any,
    max_slots: int = COMPLETION_MERGE_SLOT_COUNT,
) -> dict[str, str]:
    """Indexed merge codes for completion statement tables in the universal template."""
    fields: dict[str, str] = {
        "[COMPLETION_DATE]": statement_date.strftime("%d %B %Y"),
    }
    table_rows: list[tuple[str, str, str]] = []
    total_dr = total_cr = 0
    categories = getattr(finance, "categories", None) or []
    for cat in categories:
        cat_name = (getattr(cat, "name", None) or str(cat)).strip()
        if cat_name:
            table_rows.append((cat_name.upper(), "", ""))
        items = getattr(cat, "items", None) or []
        for item in items:
            for desc, debit_pence, credit_pence in finance_item_completion_rows(item):
                debit_s = format_gbp_pence(debit_pence) if debit_pence else ""
                credit_s = format_gbp_pence(credit_pence) if credit_pence else ""
                total_dr += debit_pence
                total_cr += credit_pence
                table_rows.append((desc, debit_s, credit_s))

    used = 0
    for i, (desc, debit, credit) in enumerate(table_rows, start=1):
        if i > max_slots:
            break
        used = i
        tag = f"{i:02d}"
        fields[f"[COMPLETION_{tag}_DESCRIPTION]"] = desc
        fields[f"[COMPLETION_{tag}_DEBIT]"] = debit
        fields[f"[COMPLETION_{tag}_CREDIT]"] = credit

    balance = total_cr - total_dr
    if balance > 0:
        balance_label = "BALANCE DUE FROM CLIENT"
    elif balance < 0:
        balance_label = "BALANCE DUE TO CLIENT"
    else:
        balance_label = "BALANCE"

    fields["[COMPLETION_TOTAL_DEBIT]"] = format_gbp_pence(total_dr)
    fields["[COMPLETION_TOTAL_CREDIT]"] = format_gbp_pence(total_cr)
    fields["[COMPLETION_BALANCE_LABEL]"] = balance_label
    fields["[COMPLETION_BALANCE_AMOUNT]"] = format_gbp_pence(abs(balance))

    for i in range(used + 1, max_slots + 1):
        tag = f"{i:02d}"
        fields[f"[COMPLETION_{tag}_DESCRIPTION]"] = ""
        fields[f"[COMPLETION_{tag}_DEBIT]"] = ""
        fields[f"[COMPLETION_{tag}_CREDIT]"] = ""
    return fields


def strip_empty_completion_table_rows(doc_bytes: bytes) -> bytes:
    """Remove completion-table rows with no merged content (empty cells or leftover slot placeholders)."""
    import io

    from docx import Document

    doc = Document(io.BytesIO(doc_bytes))
    changed = False

    def _row_blank(cells: list) -> bool:
        texts = [(c.text or "").strip() for c in cells]
        if any(_COMPLETION_SLOT_TOKEN_RE.match(t) for t in texts):
            return True
        return not any(texts)

    def _process_table(table: Any) -> None:
        nonlocal changed
        remove_indices: list[int] = []
        for ri, row in enumerate(table.rows):
            if ri == 0:
                continue
            if _row_blank(row.cells):
                remove_indices.append(ri)
        for ri in reversed(remove_indices):
            table._tbl.remove(table.rows[ri]._tr)
            changed = True

    for table in doc.tables:
        _process_table(table)
    for section in doc.sections:
        for hf in (
            section.header,
            section.footer,
            section.even_page_header,
            section.even_page_footer,
            section.first_page_header,
            section.first_page_footer,
        ):
            if hf.is_linked_to_previous:
                continue
            for table in hf.tables:
                _process_table(table)

    if not changed:
        return doc_bytes
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()

def write_completion_statement_docx(
    path: Path,
    *,
    case_number: str,
    client_name: str | None,
    finance: Any,  # FinanceOut (or dict with .categories list)
) -> None:
    """Write a completion statement .docx from case finance data."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor, Inches
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    def _fmt_pence(p: int | None) -> str:
        if p is None:
            return ""
        val = abs(p) / 100
        return f"\u00a3{val:,.2f}"  # £ with thousands separator

    def _set_cell_shading(cell, fill: str) -> None:
        """Apply a background fill colour (hex) to a table cell."""
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), fill)
        tcPr.append(shd)

    def _set_cell_borders(cell, top=None, bottom=None, left=None, right=None) -> None:
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        tcBorders = OxmlElement("w:tcBorders")
        for side, val in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
            if val:
                el = OxmlElement(f"w:{side}")
                el.set(qn("w:val"), val.get("val", "single"))
                el.set(qn("w:sz"), str(val.get("sz", 4)))
                el.set(qn("w:space"), "0")
                el.set(qn("w:color"), val.get("color", "auto"))
                tcBorders.append(el)
        tcPr.append(tcBorders)

    doc = Document()
    _set_default_proofing_language_en_gb(doc)

    # ── Page margins ──────────────────────────────────────────────────────────
    for section in doc.sections:
        section.top_margin = Inches(0.9)
        section.bottom_margin = Inches(0.9)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    # ── Title ─────────────────────────────────────────────────────────────────
    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title_para.add_run("COMPLETION STATEMENT")
    run.bold = True
    run.font.size = Pt(16)

    # ── Sub-header: matter reference + date ───────────────────────────────────
    matter_line = case_number
    if client_name:
        matter_line = f"{case_number} — {client_name}"
    sub_para = doc.add_paragraph()
    sub_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub_run = sub_para.add_run(matter_line)
    sub_run.font.size = Pt(11)

    date_para = doc.add_paragraph()
    date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date_run = date_para.add_run(f"Date: {date.today().strftime('%d %B %Y')}")
    date_run.font.size = Pt(10)
    date_run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

    doc.add_paragraph()  # spacer

    # ── Main table ────────────────────────────────────────────────────────────
    # Columns: Description | Debit | Credit
    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"

    # Header row
    hdr_cells = table.rows[0].cells
    for i, label in enumerate(("Description", "Debit", "Credit")):
        cell = hdr_cells[i]
        cell.text = label
        run = cell.paragraphs[0].runs[0]
        run.bold = True
        run.font.size = Pt(10)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER if i > 0 else WD_ALIGN_PARAGRAPH.LEFT
        _set_cell_shading(cell, "D0DAEA")

    # Column widths (Description wide, Debit/Credit equal)
    col_widths = [Inches(3.8), Inches(1.5), Inches(1.5)]
    for i, width in enumerate(col_widths):
        for row in table.rows:
            row.cells[i].width = width

    total_dr = 0
    total_cr = 0

    categories = getattr(finance, "categories", None) or []

    for cat in categories:
        cat_name = getattr(cat, "name", None) or str(cat)
        items = getattr(cat, "items", None) or []

        # Category header row
        row = table.add_row()
        row.cells[0].merge(row.cells[2])
        merged = row.cells[0]
        merged.text = cat_name.upper()
        run = merged.paragraphs[0].runs[0]
        run.bold = True
        run.font.size = Pt(9)
        _set_cell_shading(merged, "EEF2F8")

        for item in items:
            for desc, debit_pence, credit_pence in finance_item_completion_rows(item):
                debit_str = _fmt_pence(debit_pence) if debit_pence else ""
                credit_str = _fmt_pence(credit_pence) if credit_pence else ""
                total_dr += debit_pence
                total_cr += credit_pence

                row = table.add_row()
                row.cells[0].text = desc
                row.cells[0].paragraphs[0].runs[0].font.size = Pt(10)
                row.cells[1].text = debit_str
                row.cells[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
                row.cells[1].paragraphs[0].runs[0 if row.cells[1].paragraphs[0].runs else -1].font.size = Pt(10) if row.cells[1].paragraphs[0].runs else None
                row.cells[2].text = credit_str
                row.cells[2].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
                if row.cells[2].paragraphs[0].runs:
                    row.cells[2].paragraphs[0].runs[0].font.size = Pt(10)
                for ci in range(3):
                    if row.cells[ci].paragraphs[0].runs:
                        row.cells[ci].paragraphs[0].runs[0].font.size = Pt(10)

    # ── Totals row ────────────────────────────────────────────────────────────
    tot_row = table.add_row()
    tot_row.cells[0].text = "TOTALS"
    tot_row.cells[1].text = _fmt_pence(total_dr)
    tot_row.cells[2].text = _fmt_pence(total_cr)
    for ci, cell in enumerate(tot_row.cells):
        run = cell.paragraphs[0].runs[0] if cell.paragraphs[0].runs else cell.paragraphs[0].add_run(cell.text)
        run.bold = True
        run.font.size = Pt(10)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT if ci > 0 else WD_ALIGN_PARAGRAPH.LEFT
        _set_cell_shading(cell, "D0DAEA")

    # ── Balance row ───────────────────────────────────────────────────────────
    balance = total_cr - total_dr
    bal_row = table.add_row()
    bal_row.cells[0].merge(bal_row.cells[1])
    bal_label = bal_row.cells[0]
    bal_label.text = "BALANCE DUE FROM CLIENT" if balance > 0 else "BALANCE DUE TO CLIENT" if balance < 0 else "BALANCE"
    bal_run = bal_label.paragraphs[0].runs[0] if bal_label.paragraphs[0].runs else bal_label.paragraphs[0].add_run(bal_label.text)
    bal_run.bold = True
    bal_run.font.size = Pt(10)
    _set_cell_shading(bal_label, "EEF2F8")

    bal_val_cell = bal_row.cells[2]
    bal_val_cell.text = _fmt_pence(abs(balance))
    bal_val_run = bal_val_cell.paragraphs[0].runs[0] if bal_val_cell.paragraphs[0].runs else bal_val_cell.paragraphs[0].add_run(bal_val_cell.text)
    bal_val_run.bold = True
    bal_val_run.font.size = Pt(10)
    bal_val_cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _set_cell_shading(bal_val_cell, "EEF2F8")

    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
