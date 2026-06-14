"""Generate completion statement .docx files from the universal precedent template."""

from __future__ import annotations

import os
import tempfile
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.docx_util import (
    build_merge_fields,
    completion_line_merge_fields,
    ensure_docx_proofing_language_en_gb_bytes,
    merge_precedent_codes,
    strip_empty_completion_table_rows,
    write_completion_statement_docx,
)
from app.finance_service import get_finance
from app.global_precedent_loader import load_global_precedent_docx_bytes
from app.models import Case, FirmSettings, User
from app.precedent_constants import COMPLETION_STATEMENT_PRECEDENT_REFERENCE


def _firm_settings(db: Session) -> FirmSettings:
    row = db.get(FirmSettings, 1)
    if row is None:
        row = FirmSettings(id=1)
        db.add(row)
        db.flush()
    return row


def _fee_earner_name(case: Case, db: Session) -> str:
    u = db.get(User, case.fee_earner_user_id) if case.fee_earner_user_id else None
    if not u:
        return ""
    return (u.display_name or u.email or "").strip()


def build_completion_statement_docx_bytes(case: Case, db: Session) -> bytes:
    finance = get_finance(case.id, db)
    statement_date = date.today()
    firm = _firm_settings(db)
    fe_name = _fee_earner_name(case, db)

    template_bytes = load_global_precedent_docx_bytes(db, COMPLETION_STATEMENT_PRECEDENT_REFERENCE)
    if template_bytes is not None:
        fields = build_merge_fields(
            case,
            fee_earner_name=fe_name,
            merge_date=statement_date,
            firm=firm,
        )
        fields.update(
            completion_line_merge_fields(
                statement_date=statement_date,
                finance=finance,
            )
        )
        docx_bytes = merge_precedent_codes(template_bytes, fields)
        docx_bytes = strip_empty_completion_table_rows(docx_bytes)
        return ensure_docx_proofing_language_en_gb_bytes(docx_bytes)

    fd, tmp_name = tempfile.mkstemp(suffix=".docx")
    tmp = Path(tmp_name)
    try:
        os.close(fd)
        write_completion_statement_docx(
            tmp,
            case_number=case.case_number,
            client_name=case.client_name,
            finance=finance,
        )
        return tmp.read_bytes()
    finally:
        tmp.unlink(missing_ok=True)
