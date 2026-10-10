"""Firm-wide staff feed of outstanding / completed portal client actions."""

from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.canary_sign_service import list_signing_menu_rows
from app.commercial_hooks import docusign_enabled, list_docusign_menu_rows
from app.deps import get_case_if_accessible
from app.models import (
    CanarySignStatus,
    Case,
    Contact,
    File,
    PortalFormSubmission,
    PortalFormSubmissionStatus,
    PortalFormTemplate,
    QuotePortalDelivery,
    QuotePortalDeliveryStatus,
    User,
)
from app.portal_case import firm_canary_sign_enabled, firm_client_portal_enabled
from app.portal_service import contact_display_name
from app.schemas.portal_summary import (
    PortalSummaryBucket,
    PortalSummaryKind,
    PortalSummaryOptionsOut,
    PortalSummaryRowOut,
)

PortalSummaryKindFilter = PortalSummaryKind | None


def portal_summary_options(db: Session) -> PortalSummaryOptionsOut:
    portal_on = firm_client_portal_enabled(db)
    canary_on = firm_canary_sign_enabled(db)
    docusign_on = docusign_enabled(db)
    return PortalSummaryOptionsOut(
        enabled=bool(portal_on or canary_on or docusign_on),
        client_portal_enabled=portal_on,
        canary_sign_enabled=canary_on,
        docusign_enabled=docusign_on,
    )


def _row(
    *,
    kind: PortalSummaryKind,
    id: uuid.UUID,
    case: Case,
    title: str,
    status: str,
    contact_or_recipients: str = "",
    sent_by_display_name: str | None = None,
    created_at: datetime | None = None,
) -> PortalSummaryRowOut:
    return PortalSummaryRowOut(
        kind=kind,
        id=id,
        case_id=case.id,
        case_number=case.case_number,
        client_name=case.client_name,
        matter_description=(case.title or "").strip(),
        title=title,
        status=status,
        contact_or_recipients=contact_or_recipients,
        sent_by_display_name=sent_by_display_name,
        created_at=created_at,
    )


def _sender_map(db: Session, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not user_ids:
        return {}
    out: dict[uuid.UUID, str] = {}
    for u in db.execute(select(User).where(User.id.in_(user_ids))).scalars():
        out[u.id] = u.display_name or u.email
    return out


def _contact_map(db: Session, contact_ids: set[uuid.UUID]) -> dict[uuid.UUID, Contact]:
    if not contact_ids:
        return {}
    return {
        c.id: c
        for c in db.execute(select(Contact).where(Contact.id.in_(contact_ids))).scalars()
    }


def _accessible_case(db: Session, user: User, case_id: uuid.UUID, cache: dict[uuid.UUID, Case | None]) -> Case | None:
    if case_id in cache:
        return cache[case_id]
    case = get_case_if_accessible(case_id, user, db)
    cache[case_id] = case
    return case


def _collect_quotes(
    db: Session,
    *,
    user: User,
    bucket: PortalSummaryBucket,
    case_cache: dict[uuid.UUID, Case | None],
) -> list[PortalSummaryRowOut]:
    if bucket == "outstanding":
        statuses = (QuotePortalDeliveryStatus.pending,)
    else:
        statuses = (QuotePortalDeliveryStatus.accepted,)
    rows = db.execute(
        select(QuotePortalDelivery, File)
        .join(File, File.id == QuotePortalDelivery.file_id)
        .where(QuotePortalDelivery.status.in_(statuses))
        .order_by(QuotePortalDelivery.sent_at.desc())
    ).all()
    if not rows:
        return []
    contact_ids = {d.contact_id for d, _ in rows if d.contact_id}
    contacts = _contact_map(db, contact_ids)
    sender_ids = {d.sent_by_user_id for d, _ in rows if d.sent_by_user_id}
    senders = _sender_map(db, sender_ids)
    out: list[PortalSummaryRowOut] = []
    for delivery, frow in rows:
        case = _accessible_case(db, user, delivery.case_id, case_cache)
        if case is None:
            continue
        contact = contacts.get(delivery.contact_id)
        out.append(
            _row(
                kind="quote",
                id=delivery.id,
                case=case,
                title=(frow.original_filename or "Quote").strip() or "Quote",
                status=delivery.status.value,
                contact_or_recipients=contact_display_name(contact) if contact else "",
                sent_by_display_name=senders.get(delivery.sent_by_user_id) if delivery.sent_by_user_id else None,
                created_at=delivery.sent_at,
            )
        )
    return out


def _collect_forms(
    db: Session,
    *,
    user: User,
    bucket: PortalSummaryBucket,
    case_cache: dict[uuid.UUID, Case | None],
) -> list[PortalSummaryRowOut]:
    if bucket == "outstanding":
        statuses = (PortalFormSubmissionStatus.pending,)
    else:
        statuses = (PortalFormSubmissionStatus.completed,)
    rows = db.execute(
        select(PortalFormSubmission, PortalFormTemplate)
        .join(PortalFormTemplate, PortalFormTemplate.id == PortalFormSubmission.template_id)
        .where(PortalFormSubmission.status.in_(statuses))
        .order_by(PortalFormSubmission.sent_at.desc())
    ).all()
    if not rows:
        return []
    contact_ids = {s.contact_id for s, _ in rows if s.contact_id}
    contacts = _contact_map(db, contact_ids)
    sender_ids = {s.sent_by_user_id for s, _ in rows if s.sent_by_user_id}
    senders = _sender_map(db, sender_ids)
    out: list[PortalSummaryRowOut] = []
    for sub, template in rows:
        case = _accessible_case(db, user, sub.case_id, case_cache)
        if case is None:
            continue
        contact = contacts.get(sub.contact_id)
        out.append(
            _row(
                kind="form",
                id=sub.id,
                case=case,
                title=(template.name or "Form").strip() or "Form",
                status=sub.status.value,
                contact_or_recipients=contact_display_name(contact) if contact else "",
                sent_by_display_name=senders.get(sub.sent_by_user_id) if sub.sent_by_user_id else None,
                created_at=sub.sent_at,
            )
        )
    return out


def _collect_canary_sign(
    db: Session,
    *,
    user: User,
    bucket: PortalSummaryBucket,
) -> list[PortalSummaryRowOut]:
    status = CanarySignStatus.pending if bucket == "outstanding" else CanarySignStatus.completed
    rows = list_signing_menu_rows(db, user=user, status_filter=status)
    out: list[PortalSummaryRowOut] = []
    for r in rows:
        out.append(
            PortalSummaryRowOut(
                kind="canary_sign",
                id=r["id"],
                case_id=r["case_id"],
                case_number=r.get("case_number"),
                client_name=r.get("client_name"),
                matter_description=(r.get("matter_description") or "").strip(),
                title=(r.get("subject") or "Document to sign").strip() or "Document to sign",
                status=str(r.get("status") or ""),
                contact_or_recipients=(r.get("recipients_summary") or "").strip(),
                sent_by_display_name=r.get("sent_by_display_name"),
                created_at=r.get("created_at"),
            )
        )
    return out


def _collect_docusign(
    db: Session,
    *,
    user: User,
    bucket: PortalSummaryBucket,
) -> list[PortalSummaryRowOut]:
    if not docusign_enabled(db):
        return []
    status = "pending" if bucket == "outstanding" else "completed"
    rows = list_docusign_menu_rows(db, user=user, status_filter=status)
    out: list[PortalSummaryRowOut] = []
    for r in rows:
        out.append(
            PortalSummaryRowOut(
                kind="docusign",
                id=r["id"],
                case_id=r["case_id"],
                case_number=r.get("case_number"),
                client_name=r.get("client_name"),
                matter_description=(r.get("matter_description") or "").strip(),
                title=(r.get("envelope_subject") or "Document to sign").strip() or "Document to sign",
                status=str(r.get("status") or ""),
                contact_or_recipients=(r.get("recipients_summary") or "").strip(),
                sent_by_display_name=r.get("sent_by_display_name"),
                created_at=r.get("created_at"),
            )
        )
    return out


def list_portal_summary(
    db: Session,
    *,
    user: User,
    bucket: PortalSummaryBucket = "outstanding",
    kind: PortalSummaryKindFilter = None,
) -> list[PortalSummaryRowOut]:
    """Union of portal client actions the staff user can access."""
    opts = portal_summary_options(db)
    case_cache: dict[uuid.UUID, Case | None] = {}
    rows: list[PortalSummaryRowOut] = []

    include_portal_kinds = opts.client_portal_enabled
    if kind is None or kind == "quote":
        if include_portal_kinds:
            rows.extend(_collect_quotes(db, user=user, bucket=bucket, case_cache=case_cache))
    if kind is None or kind == "form":
        if include_portal_kinds:
            rows.extend(_collect_forms(db, user=user, bucket=bucket, case_cache=case_cache))
    if kind is None or kind == "canary_sign":
        if opts.canary_sign_enabled:
            rows.extend(_collect_canary_sign(db, user=user, bucket=bucket))
    if kind is None or kind == "docusign":
        if opts.docusign_enabled:
            rows.extend(_collect_docusign(db, user=user, bucket=bucket))

    def sort_key(row: PortalSummaryRowOut) -> tuple[float, str]:
        ts = row.created_at.timestamp() if row.created_at is not None else 0.0
        return (-ts, str(row.id))

    rows.sort(key=sort_key)
    return rows
