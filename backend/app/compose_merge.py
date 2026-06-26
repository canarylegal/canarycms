"""Shared DOCX merge for Letter / Document / M365 e-mail compose flows."""

from __future__ import annotations

import logging
import os
import tempfile
import uuid
from datetime import date
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.docx_util import (
    apply_digital_letterhead_headers_footers,
    build_merge_fields,
    completion_line_merge_fields,
    ensure_docx_proofing_language_en_gb_bytes,
    fee_earner_signature_for_merge,
    inject_merge_code_images,
    invoice_line_merge_fields,
    is_invalid_ooxml_merge_exception,
    merge_precedent_codes,
    property_merge_fields,
    precedent_is_standalone_letter,
    reapply_letterhead_layout_package_bytes,
    splice_precedent_into_blank_letter,
    strip_empty_completion_table_rows,
    strip_precedent_body_marker,
    validate_docx_package_bytes,
    write_blank_docx,
)
from app.precedent_constants import (
    BLANK_LETTER_PRECEDENT_REFERENCE,
    COMPLETION_STATEMENT_PRECEDENT_REFERENCE,
    INVOICE_TEMPLATE_PRECEDENT_REFERENCE,
    SYSTEM_DOCUMENT_TEMPLATE_REFERENCES,
)
from app.file_storage import FILES_ROOT
from app.matter_contact_constants import CLIENT_SLUG, LAWYERS_SLUG, normalize_matter_contact_type_slug
from app.models import Case as CaseModel
from app.models import (
    CaseContact,
    Contact as GlobalContact,
    File as DbFile,
    FirmSettings,
    LetterheadStyle,
    Precedent,
    PrecedentKind,
    User,
)
from app.schemas import ComposeOfficeDocumentIn

log = logging.getLogger(__name__)


def _effective_compose_office_role(body: ComposeOfficeDocumentIn) -> str | None:
    """Letter vs document when ``compose_office_role`` is omitted.

    The web UI names new files ``Letter — ….docx`` and ``Document — ….docx``. Older clients (or proxies)
    may omit ``compose_office_role``; without this, letter compose with “Blank (no precedent)” would fall
    through to :func:`write_blank_docx` instead of the ``BLANK_LETTER`` template.
    """

    if body.compose_office_role is not None:
        return body.compose_office_role
    stem = Path(body.original_filename or "").stem.strip().lower().replace("\u00a0", " ").strip()
    if stem.startswith("letter"):
        return "letter"
    if stem.startswith("document"):
        return "document"
    return None


def _is_letter_compose_role(role: str | None) -> bool:
    return role == "letter"


def _read_firm_letterhead_file_bytes(db: Session, file_id: uuid.UUID | None) -> bytes | None:
    if file_id is None:
        return None
    lh_file = db.get(DbFile, file_id)
    if lh_file is None:
        return None
    lh_abs = (FILES_ROOT / lh_file.storage_path).resolve()
    if not str(lh_abs).startswith(str(FILES_ROOT)) or not lh_abs.is_file():
        return None
    try:
        return lh_abs.read_bytes()
    except OSError as exc:
        log.warning("letterhead file read failed: %s", exc)
        return None


def finalize_digital_letterhead_docx(src_bytes: bytes, lh_bytes: bytes | None) -> bytes:
    """Apply en-GB proofing, then restore letterhead layout metadata proofing may override."""
    src_bytes = ensure_docx_proofing_language_en_gb_bytes(src_bytes)
    if lh_bytes is not None:
        src_bytes = reapply_letterhead_layout_package_bytes(src_bytes, lh_bytes)
    return src_bytes


def apply_quote_digital_letterhead_from_settings(
    db: Session,
    *,
    firm_row: FirmSettings | None,
    src_bytes: bytes,
) -> tuple[bytes, bytes | None]:
    """Overlay quote letterhead headers/footers onto the quote document body (fee-scale compose)."""
    if firm_row is None:
        return src_bytes, None
    if firm_row.quote_letterhead_style != LetterheadStyle.digital:
        return src_bytes, None
    lh_bytes = _read_firm_letterhead_file_bytes(db, firm_row.quote_letterhead_file_id)
    if lh_bytes is None:
        return src_bytes, None
    try:
        return apply_digital_letterhead_headers_footers(src_bytes, lh_bytes), lh_bytes
    except Exception as lh_exc:
        log.warning("quote digital letterhead merge failed: %s", lh_exc)
        return src_bytes, None


def _apply_configured_digital_letterhead(
    db: Session,
    *,
    body: ComposeOfficeDocumentIn,
    src_bytes: bytes,
    firm_row: FirmSettings | None,
    prec_kind: PrecedentKind | None = None,
) -> tuple[bytes, bytes | None]:
    """Overlay firm letterhead headers/footers when digital mode is enabled."""
    if firm_row is None:
        return src_bytes, None
    if prec_kind is not None and prec_kind != PrecedentKind.letter:
        return src_bytes, None
    role = _effective_compose_office_role(body)
    if not _is_letter_compose_role(role):
        return src_bytes, None
    lh_style = firm_row.letterhead_style
    lh_file_id = firm_row.letterhead_file_id
    if lh_style != LetterheadStyle.digital or lh_file_id is None:
        return src_bytes, None
    lh_bytes = _read_firm_letterhead_file_bytes(db, lh_file_id)
    if lh_bytes is None:
        return src_bytes, None
    try:
        return apply_digital_letterhead_headers_footers(src_bytes, lh_bytes), lh_bytes
    except Exception as lh_exc:
        log.warning("digital letterhead merge failed: %s", lh_exc)
        return src_bytes, None


def _resolve_blank_letter_precedent_body(db: Session, body: ComposeOfficeDocumentIn) -> ComposeOfficeDocumentIn:
    """If letter compose with no precedent id, use reserved ``BLANK_LETTER`` precedent when present."""

    if body.precedent_id is not None:
        return body
    if not _is_letter_compose_role(_effective_compose_office_role(body)):
        return body
    blank = _load_blank_letter_precedent(db)
    if blank is None:
        return body
    return body.model_copy(update={"precedent_id": blank.id})


def _load_blank_letter_precedent(db: Session) -> Precedent | None:
    """Return the reserved ``BLANK_LETTER`` precedent row, or ``None`` if absent."""

    return db.execute(
        select(Precedent)
        .where(
            Precedent.reference == BLANK_LETTER_PRECEDENT_REFERENCE,
            Precedent.kind == PrecedentKind.letter,
        )
        .order_by(Precedent.created_at.asc())
        .limit(1)
    ).scalars().first()


def _load_blank_letter_bytes(db: Session) -> bytes | None:
    """Read the reserved blank-letter .docx off disk, or ``None`` if missing/unreadable."""

    blank = _load_blank_letter_precedent(db)
    if blank is None:
        return None
    bfile = db.get(DbFile, blank.file_id)
    if bfile is None:
        return None
    abs_path = (FILES_ROOT / bfile.storage_path).resolve()
    if not str(abs_path).startswith(str(FILES_ROOT)) or not abs_path.is_file():
        return None
    try:
        return abs_path.read_bytes()
    except OSError as exc:
        log.warning("blank-letter overlay: cannot read %s: %s", abs_path, exc)
        return None


def merge_compose_docx_bytes(
    db: Session,
    case_id: uuid.UUID,
    body: ComposeOfficeDocumentIn,
    *,
    require_precedent_kind: PrecedentKind | None = None,
) -> tuple[bytes, str]:
    """Return merged DOCX bytes and MIME type (always OOXML wordprocessing)."""
    body = _resolve_blank_letter_precedent_body(db, body)
    if body.precedent_id is not None:
        prec = db.get(Precedent, body.precedent_id)
        if prec is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Precedent not found")
        if require_precedent_kind is not None and prec.kind != require_precedent_kind:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"This action requires a {require_precedent_kind.value} precedent.",
            )
        pfile = db.get(DbFile, prec.file_id)
        if pfile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Precedent file missing")
        prec_abs = (FILES_ROOT / pfile.storage_path).resolve()
        if not str(prec_abs).startswith(str(FILES_ROOT)) or not prec_abs.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Precedent file missing on disk")
        src_bytes = prec_abs.read_bytes()
        mime = pfile.mime_type or "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        try:
            validate_docx_package_bytes(src_bytes)
        except ValueError as ve:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve)) from ve

        # BLANK_LETTER acts as the universal scaffold for every letter precedent. We use BLANK_LETTER
        # as the base document (so its headers/footers, page geometry, AND body merge codes — address
        # block, date, refs, salutation, Re: line, etc. — all carry through) and splice the chosen
        # precedent's body block elements into it. Merge-code substitution then resolves every token
        # in the combined document in one pass. Skipped when the chosen precedent IS the blank letter
        # (no-op) or when no blank-letter template exists. Document/email composes are unaffected.
        if (
            prec.kind == PrecedentKind.letter
            and prec.reference != BLANK_LETTER_PRECEDENT_REFERENCE
            and not precedent_is_standalone_letter(src_bytes)
        ):
            blank_bytes = _load_blank_letter_bytes(db)
            if blank_bytes is not None:
                try:
                    src_bytes = splice_precedent_into_blank_letter(blank_bytes, src_bytes)
                except Exception as overlay_exc:
                    log.warning(
                        "blank-letter scaffold splice failed precedent_id=%s: %s",
                        prec.id,
                        overlay_exc,
                    )

        # Defensive: ensure no literal [PRECEDENT_BODY] token survives into the composed letter. This
        # covers the "Blank (no precedent)" path (splice skipped) and any edge case where the splice
        # didn't find/replace the marker.
        if prec.kind == PrecedentKind.letter:
            try:
                src_bytes = strip_precedent_body_marker(src_bytes)
            except Exception as strip_exc:
                log.warning(
                    "strip_precedent_body_marker failed precedent_id=%s: %s",
                    prec.id,
                    strip_exc,
                )

        firm_row = db.execute(select(FirmSettings).where(FirmSettings.id == 1)).scalar_one_or_none()

        case_row = db.get(CaseModel, case_id)
        contact = None
        if body.case_contact_id:
            contact = db.get(CaseContact, body.case_contact_id)
        elif body.global_contact_id:
            contact = db.get(GlobalContact, body.global_contact_id)

        client_ccs: list[CaseContact] = []
        cc_rows: list[CaseContact] = []
        if case_row:
            cc_rows = (
                db.execute(
                    select(CaseContact)
                    .where(CaseContact.case_id == case_id)
                    .order_by(CaseContact.created_at.asc())
                )
                .scalars()
                .all()
            )
            client_ccs = [
                c for c in cc_rows if normalize_matter_contact_type_slug(c.matter_contact_type) == CLIENT_SLUG
            ]
        oc = client_ccs[:4]

        lawyer_rows = [
            c for c in cc_rows if normalize_matter_contact_type_slug(c.matter_contact_type) == LAWYERS_SLUG
        ]
        lawyer_rows = sorted(lawyer_rows, key=lambda c: c.created_at)[:4]
        lawyer_slot_list: list[tuple[CaseContact, list[CaseContact]] | None] = []
        for lr in lawyer_rows:
            raw_ids = lr.lawyer_client_ids or []
            loaded: list[CaseContact] = []
            for sid in raw_ids[:4]:
                try:
                    uid = uuid.UUID(str(sid))
                except (ValueError, TypeError):
                    continue
                row_cc = db.get(CaseContact, uid)
                if row_cc and row_cc.case_id == case_id and row_cc.id != lr.id:
                    loaded.append(row_cc)
            lawyer_slot_list.append((lr, loaded))
        while len(lawyer_slot_list) < 4:
            lawyer_slot_list.append(None)

        fee_earner_name = ""
        fee_earner_job_title = ""
        fee_earner_initials = ""
        if case_row and case_row.fee_earner_user_id:
            fe_user = db.get(User, case_row.fee_earner_user_id)
            if fe_user:
                fee_earner_name = fe_user.display_name or fe_user.email or ""
                fee_earner_job_title = (fe_user.job_title or "").strip()
                fee_earner_initials = (fe_user.initials or "").strip()

        merge_all = body.precedent_merge_all_clients
        selected_slot: int | None = None
        if not merge_all and contact is not None and body.case_contact_id is not None:
            cc_row = contact
            if isinstance(cc_row, CaseContact) and normalize_matter_contact_type_slug(cc_row.matter_contact_type) == CLIENT_SLUG:
                idx0 = next((i for i, c in enumerate(client_ccs) if c.id == cc_row.id), None)
                if idx0 is not None and idx0 < 4:
                    selected_slot = idx0 + 1

        should_merge = (
            merge_all
            or body.case_contact_id is not None
            or body.global_contact_id is not None
            or prec.reference in SYSTEM_DOCUMENT_TEMPLATE_REFERENCES
        )
        if should_merge:
            statement_date = date.today()
            fields = build_merge_fields(
                case_row,
                fee_earner_name=fee_earner_name,
                fee_earner_job_title=fee_earner_job_title,
                fee_earner_initials=fee_earner_initials,
                merge_date=statement_date if prec.reference == COMPLETION_STATEMENT_PRECEDENT_REFERENCE else None,
                merge_all_clients=merge_all,
                ordered_client_contacts=oc,
                selected_contact=None if merge_all else contact,
                selected_client_slot=None if merge_all else selected_slot,
                lawyer_slots=lawyer_slot_list,
                compose_selected_contact=contact,
                firm=firm_row,
            )
            if prec.reference == COMPLETION_STATEMENT_PRECEDENT_REFERENCE:
                from app.finance_service import get_finance

                fields.update(
                    completion_line_merge_fields(
                        statement_date=statement_date,
                        finance=get_finance(case_id, db),
                    )
                )
            elif prec.reference == INVOICE_TEMPLATE_PRECEDENT_REFERENCE:
                bill_to = (case_row.client_name or "").strip() if case_row else ""
                fields.update(
                    invoice_line_merge_fields(
                        invoice_number="",
                        invoice_date=statement_date,
                        bill_to_name=bill_to,
                        lines=[],
                        total_pence=0,
                    )
                )
            fields.update(property_merge_fields(db, case_id))
            template_has_org_addr = b"[ORG_AND_ADDRESS_BLOCK]" in src_bytes
            try:
                src_bytes = merge_precedent_codes(
                    src_bytes,
                    fields,
                    ordered_clients=oc,
                    merge_all_clients=merge_all,
                )
                sig = fee_earner_signature_for_merge(db, case_row.fee_earner_user_id if case_row else None)
                if sig:
                    sig_path, sig_width = sig
                    src_bytes = inject_merge_code_images(
                        src_bytes,
                        {"[FEE_EARNER_SIGNATURE]": sig_path},
                        width_inches={"[FEE_EARNER_SIGNATURE]": sig_width},
                    )
            except Exception as exc:
                if is_invalid_ooxml_merge_exception(exc):
                    log.warning("merge_precedent_codes: invalid or unreadable .docx: %s", exc)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "The precedent is not a valid Word .docx (ZIP/OXML error). "
                            "Upload a real .docx from Word (Save As → Word Document), not a renamed .doc or HTML download. "
                            f"Detail: {exc!s}"
                        ),
                    ) from exc
                log.exception("merge_precedent_codes failed")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Precedent merge failed: {exc}",
                ) from exc
            if prec.reference == COMPLETION_STATEMENT_PRECEDENT_REFERENCE:
                src_bytes = strip_empty_completion_table_rows(src_bytes)
            if template_has_org_addr and b"[ORG_AND_ADDRESS_BLOCK]" in src_bytes:
                log.error(
                    "compose merge left literal [ORG_AND_ADDRESS_BLOCK] precedent_id=%s path=%s",
                    prec.id,
                    pfile.storage_path,
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "Merge did not replace [ORG_AND_ADDRESS_BLOCK]. The template may have been altered "
                        "(e.g. by an editor splitting tokens across XML runs)."
                    ),
                )

        src_bytes, lh_bytes = _apply_configured_digital_letterhead(
            db,
            body=body,
            src_bytes=src_bytes,
            firm_row=firm_row,
            prec_kind=prec.kind,
        )

        src_bytes = finalize_digital_letterhead_docx(src_bytes, lh_bytes)
        return src_bytes, mime

    fd, tmp_name = tempfile.mkstemp(suffix=".docx")
    tmp = Path(tmp_name)
    try:
        os.close(fd)
        write_blank_docx(tmp)
        src_bytes = tmp.read_bytes()
    finally:
        tmp.unlink(missing_ok=True)
    firm_row = db.execute(select(FirmSettings).where(FirmSettings.id == 1)).scalar_one_or_none()
    src_bytes, lh_bytes = _apply_configured_digital_letterhead(
        db,
        body=body,
        src_bytes=src_bytes,
        firm_row=firm_row,
        prec_kind=PrecedentKind.letter if _is_letter_compose_role(_effective_compose_office_role(body)) else None,
    )
    src_bytes = _finalize_digital_letterhead_docx(src_bytes, lh_bytes)
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return src_bytes, mime
