"""Create case quote documents from native fee scale definitions."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compose_merge import apply_quote_digital_letterhead_from_settings, finalize_digital_letterhead_docx
from app.global_precedent_loader import load_global_precedent_docx_bytes
from app.docx_util import (
    QUOTE_MERGE_SLOT_COUNT,
    apply_quote_table_presentation,
    build_merge_fields,
    fee_earner_signature_for_merge,
    format_gbp_pence,
    inject_merge_code_images,
    merge_precedent_codes,
    strip_empty_quote_table_rows,
    validate_docx_package_bytes,
    write_quote_template_docx_bytes,
)
from app.fee_scale_calc import ComputedQuoteLine, quote_column_totals
from app.fee_scale_service import fee_scale_matches_case, preview_quote_draft, preview_quote_lines
from app.file_storage import FILES_ROOT
from app.matter_contact_constants import CLIENT_SLUG, LAWYERS_SLUG, normalize_matter_contact_type_slug
from app.models import Case as CaseModel
from app.models import CaseContact, Contact as GlobalContact, FeeScale, File as DbFile, FirmSettings, User
from app.precedent_constants import QUOTE_TEMPLATE_PRECEDENT_REFERENCE
from app.schemas import ComposeQuoteIn, ComposeQuoteLineIn


def _load_quote_template_bytes(db: Session, firm_row: FirmSettings | None) -> bytes:
    template = load_global_precedent_docx_bytes(db, QUOTE_TEMPLATE_PRECEDENT_REFERENCE)
    if template is not None:
        return template
    if firm_row and firm_row.quote_letterhead_file_id:
        lh_file = db.get(DbFile, firm_row.quote_letterhead_file_id)
        if lh_file is not None:
            lh_abs = (FILES_ROOT / lh_file.storage_path).resolve()
            if str(lh_abs).startswith(str(FILES_ROOT)) and lh_abs.is_file():
                raw = lh_abs.read_bytes()
                try:
                    validate_docx_package_bytes(raw)
                    return raw
                except ValueError:
                    pass
    return write_quote_template_docx_bytes()


def _line_vat_pence(ln: ComputedQuoteLine | ComposeQuoteLineIn) -> int | None:
    return ln.vat_pence


def _quote_line_merge_fields(
    lines: list[ComputedQuoteLine] | list[ComposeQuoteLineIn],
    *,
    property_value_pence: int | None,
    max_slots: int = QUOTE_MERGE_SLOT_COUNT,
) -> dict[str, str]:
    """Indexed merge codes: label, main amount, VAT amount per row; column and grand totals."""
    fields: dict[str, str] = {}
    if property_value_pence is not None:
        fields["[QUOTE_PROPERTY_VALUE]"] = format_gbp_pence(property_value_pence)
    else:
        fields["[QUOTE_PROPERTY_VALUE]"] = ""

    computed_only = [ln for ln in lines if isinstance(ln, ComputedQuoteLine)]
    if computed_only:
        main_total, vat_total = quote_column_totals(computed_only)
    else:
        main_total, vat_total = 0, 0

    used = 0
    for i, ln in enumerate(lines, start=1):
        used = i
        tag = f"{i:02d}"
        kind = ln.line_kind if isinstance(ln.line_kind, str) else ln.line_kind.value
        is_bold = ln.is_bold
        name = ln.name
        amount_pence = ln.amount_pence
        vat_pence = _line_vat_pence(ln)
        fields[f"[QUOTE_{tag}_LABEL]"] = name
        if kind == "section_header":
            fields[f"[QUOTE_{tag}_AMOUNT]"] = ""
            fields[f"[QUOTE_{tag}_VAT]"] = ""
        else:
            if amount_pence is not None:
                fields[f"[QUOTE_{tag}_AMOUNT]"] = format_gbp_pence(amount_pence)
            else:
                fields[f"[QUOTE_{tag}_AMOUNT]"] = ""
            if vat_pence is not None:
                fields[f"[QUOTE_{tag}_VAT]"] = format_gbp_pence(vat_pence)
            else:
                fields[f"[QUOTE_{tag}_VAT]"] = ""
        if is_bold:
            fields[f"[b:QUOTE_{tag}_LABEL]"] = name
            if fields[f"[QUOTE_{tag}_AMOUNT]"]:
                fields[f"[b:QUOTE_{tag}_AMOUNT]"] = fields[f"[QUOTE_{tag}_AMOUNT]"]
            if fields[f"[QUOTE_{tag}_VAT]"]:
                fields[f"[b:QUOTE_{tag}_VAT]"] = fields[f"[QUOTE_{tag}_VAT]"]

    for i in range(used + 1, max_slots + 1):
        tag = f"{i:02d}"
        fields[f"[QUOTE_{tag}_LABEL]"] = ""
        fields[f"[QUOTE_{tag}_AMOUNT]"] = ""
        fields[f"[QUOTE_{tag}_VAT]"] = ""

    fields["[QUOTE_MAIN_TOTAL]"] = format_gbp_pence(main_total) if main_total else ""
    fields["[QUOTE_VAT_TOTAL]"] = format_gbp_pence(vat_total) if vat_total else ""
    grand = main_total + vat_total
    fields["[QUOTE_GRAND_TOTAL]"] = format_gbp_pence(grand) if grand else ""
    return fields


def _computed_from_compose_lines(body_lines: list[ComposeQuoteLineIn]) -> list[ComputedQuoteLine]:
    from app.models import FeeScaleLineKind

    out: list[ComputedQuoteLine] = []
    for ln in body_lines:
        try:
            kind = FeeScaleLineKind(ln.line_kind)
        except ValueError:
            kind = FeeScaleLineKind.item
        out.append(
            ComputedQuoteLine(
                line_id=None,
                name=ln.name,
                line_kind=kind,
                amount_pence=ln.amount_pence,
                vat_pence=ln.vat_pence,
                editable=False,
                is_bold=ln.is_bold,
                align_right=kind.value != "section_header",
            )
        )
    return out


def resolve_compose_quote_lines(
    db: Session,
    case_id: uuid.UUID,
    body: ComposeQuoteIn,
) -> list[ComputedQuoteLine]:
    """Compute quote display lines for compose (shared by docx merge and finance snapshot)."""
    amount_overrides = {str(k): int(v) for k, v in body.amount_overrides.items()}

    if body.draft and body.fee_scale_id is not None:
        _scale, computed, needs_pv = preview_quote_draft(
            db,
            body.fee_scale_id,
            body.draft,
            property_value_pence=body.property_value_pence,
            amount_overrides=amount_overrides,
        )
        if needs_pv and body.property_value_pence is None:
            raise ValueError(
                "Property value is required for this fee scale (banded legal fees and VAT)."
            )
        return computed
    if body.fee_scale_id is not None:
        case_row = db.get(CaseModel, case_id)
        if case_row is None:
            raise ValueError("Case not found")
        scale = db.get(FeeScale, body.fee_scale_id)
        if scale is None:
            raise ValueError("Fee scale not found")
        if not fee_scale_matches_case(
            scale,
            matter_head_type_id=case_row.matter_head_type_id,
            matter_sub_type_id=case_row.matter_sub_type_id,
        ):
            raise ValueError("Fee scale is not available for this matter type")
        overrides = _parse_overrides(body.line_overrides)
        for k, v in amount_overrides.items():
            try:
                overrides[uuid.UUID(str(k))] = int(v)
            except (ValueError, TypeError):
                continue
        _scale, computed, needs_pv = preview_quote_lines(
            db,
            body.fee_scale_id,
            property_value_pence=body.property_value_pence,
            overrides=overrides,
        )
        if needs_pv and body.property_value_pence is None:
            raise ValueError(
                "Property value is required for this fee scale (banded legal fees and VAT)."
            )
        return computed
    if body.quote_lines:
        return _computed_from_compose_lines(body.quote_lines)
    return []


def quote_lines_snapshot_payload(computed: list[ComputedQuoteLine]) -> list[dict]:
    return [
        {
            "name": ln.name,
            "line_kind": ln.line_kind.value,
            "amount_pence": ln.amount_pence,
            "vat_pence": ln.vat_pence,
            "vat_treatment": ln.vat_treatment.value if ln.vat_treatment else None,
            "is_bold": ln.is_bold,
        }
        for ln in computed
    ]


def _parse_overrides(raw: dict[str, int]) -> dict[uuid.UUID, int]:
    out: dict[uuid.UUID, int] = {}
    for k, v in raw.items():
        try:
            out[uuid.UUID(str(k))] = int(v)
        except (ValueError, TypeError):
            continue
    return out


def _build_merge_fields_for_quote(
    db: Session,
    case_id: uuid.UUID,
    body: ComposeQuoteIn,
) -> tuple[CaseModel, dict[str, str], FirmSettings | None]:
    case_row = db.get(CaseModel, case_id)
    if case_row is None:
        raise ValueError("Case not found")

    contact = None
    if body.case_contact_id:
        contact = db.get(CaseContact, body.case_contact_id)
    elif body.global_contact_id:
        contact = db.get(GlobalContact, body.global_contact_id)

    client_ccs: list[CaseContact] = []
    cc_rows = (
        db.execute(
            select(CaseContact).where(CaseContact.case_id == case_id).order_by(CaseContact.created_at.asc())
        )
        .scalars()
        .all()
    )
    client_ccs = [c for c in cc_rows if normalize_matter_contact_type_slug(c.matter_contact_type) == CLIENT_SLUG]
    oc = client_ccs[:4]

    lawyer_rows = [c for c in cc_rows if normalize_matter_contact_type_slug(c.matter_contact_type) == LAWYERS_SLUG]
    lawyer_rows = sorted(lawyer_rows, key=lambda c: c.created_at)[:4]
    lawyer_slot_list: list[tuple[CaseContact, list[CaseContact]] | None] = []
    for lr in lawyer_rows:
        loaded: list[CaseContact] = []
        for sid in (lr.lawyer_client_ids or [])[:4]:
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

    fee_earner_name = fee_earner_job_title = fee_earner_initials = ""
    if case_row.fee_earner_user_id:
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

    firm_row = db.execute(select(FirmSettings).where(FirmSettings.id == 1)).scalar_one_or_none()
    fields = build_merge_fields(
        case_row,
        fee_earner_name=fee_earner_name,
        fee_earner_job_title=fee_earner_job_title,
        fee_earner_initials=fee_earner_initials,
        merge_all_clients=merge_all,
        ordered_client_contacts=oc,
        selected_contact=None if merge_all else contact,
        selected_client_slot=None if merge_all else selected_slot,
        lawyer_slots=lawyer_slot_list,
        compose_selected_contact=contact,
        firm=firm_row,
    )
    return case_row, fields, firm_row


def merge_compose_quote_docx_bytes(
    db: Session,
    case_id: uuid.UUID,
    body: ComposeQuoteIn,
) -> tuple[bytes, str]:
    """Return merged quote .docx bytes (letterhead + fee table) and MIME type."""
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    case_row, fields, firm_row = _build_merge_fields_for_quote(db, case_id, body)

    computed = resolve_compose_quote_lines(db, case_id, body)

    docx_bytes = _load_quote_template_bytes(db, firm_row)
    quote_fields = _quote_line_merge_fields(computed, property_value_pence=body.property_value_pence)
    fields = {**fields, **quote_fields}
    docx_bytes = merge_precedent_codes(
        docx_bytes,
        fields,
        ordered_clients=[],
        merge_all_clients=body.precedent_merge_all_clients,
    )
    sig = fee_earner_signature_for_merge(db, case_row.fee_earner_user_id if case_row else None)
    if sig:
        sig_path, sig_width = sig
        docx_bytes = inject_merge_code_images(
            docx_bytes,
            {"[FEE_EARNER_SIGNATURE]": sig_path},
            width_inches={"[FEE_EARNER_SIGNATURE]": sig_width},
        )
    docx_bytes = strip_empty_quote_table_rows(docx_bytes)
    docx_bytes = apply_quote_table_presentation(docx_bytes, computed)
    docx_bytes, qlh_bytes = apply_quote_digital_letterhead_from_settings(db, firm_row=firm_row, src_bytes=docx_bytes)
    docx_bytes = finalize_digital_letterhead_docx(docx_bytes, qlh_bytes)
    return docx_bytes, mime
