"""Portal auth helpers (access code, OTP, preview / link exchange)."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alert_dispatch import AlertKind, dispatch_alert, portal_public_url
from app.audit import log_event
from app.auth_rate_limit import (
    check_portal_auth_rate_limits,
    check_portal_otp_request_rate_limits,
    check_portal_otp_verify_rate_limits,
    clear_portal_otp_verify_rate_limits,
    record_portal_auth_ip_failure,
    record_portal_otp_request_attempt,
    record_portal_otp_verify_failure,
)
from app.canary_sign_service import (
    get_recipient_by_sign_token as get_canary_recipient_by_sign_token,
    portal_signing_view as canary_portal_signing_view,
)
from app.client_ip import client_ip_from_request
from app.models import CanarySignRequest, Contact, ContactPortalAccess
from app.portal_browse_service import form_pending_out, grant_summaries, quote_delivery_view
from app.portal_case import require_case_portal_enabled
from app.portal_form_service import resolve_form_exchange_submission
from app.portal_service import (
    contact_display_name,
    contact_has_portal_content_on_case,
    find_portal_contact_by_email,
    get_matter_portal_access_by_code,
    get_portal_access_by_code,
    issue_portal_login_otp,
    matter_portal_access_is_active,
    matter_portal_session_version,
    normalize_access_code,
    portal_access_is_active,
    portal_session_version,
    record_matter_portal_auth_failure,
    record_matter_portal_auth_success,
    record_portal_auth_failure,
    record_portal_auth_success,
    verify_portal_login_otp,
)
from app.quote_portal_service import resolve_quote_exchange_delivery
from app.schemas import (
    PortalAuthIn,
    PortalAuthOut,
    PortalCanarySignExchangeIn,
    PortalCanarySignExchangeOut,
    PortalCanarySignOut,
    PortalFormExchangeIn,
    PortalFormExchangeOut,
    PortalOtpRequestIn,
    PortalOtpVerifyIn,
    PortalPreviewExchangeIn,
    PortalQuoteExchangeIn,
    PortalQuoteExchangeOut,
)
from app.security import (
    create_portal_session_token,
    decode_portal_preview_exchange_token,
)


def portal_auth(payload: PortalAuthIn, request: Request, db: Session) -> PortalAuthOut:
    ip = client_ip_from_request(request)
    check_portal_auth_rate_limits(db, ip=ip)
    code = normalize_access_code(payload.access_code)
    if len(code) < 8:
        record_portal_auth_ip_failure(db, ip=ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access code")

    matter_row = get_matter_portal_access_by_code(db, code)
    if matter_row is not None:
        if not matter_portal_access_is_active(matter_row):
            record_matter_portal_auth_failure(db, matter_row)
            record_portal_auth_ip_failure(db, ip=ip)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access code")
        contact = db.get(Contact, matter_row.contact_id)
        if contact is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access code")
        require_case_portal_enabled(db, matter_row.case_id)
        record_matter_portal_auth_success(db, matter_row)
        token = create_portal_session_token(
            contact_id=str(contact.id),
            session_version=matter_portal_session_version(matter_row),
            audience="exchange",
            case_id=str(matter_row.case_id),
        )
        log_event(
            db,
            actor_user_id=None,
            action="portal.auth.success",
            entity_type="matter_portal_access",
            entity_id=str(matter_row.id),
            meta={"contact_id": str(contact.id), "case_id": str(matter_row.case_id), "audience": "exchange"},
        )
        db.commit()
        return PortalAuthOut(
            session_token=token,
            contact_name=contact_display_name(contact),
            grants=grant_summaries(db, contact.id, case_id=matter_row.case_id),
            focus_case_id=matter_row.case_id,
            staff_preview=False,
            audience="exchange",
        )

    row = get_portal_access_by_code(db, code)
    if row is None or not portal_access_is_active(row):
        if row is not None:
            record_portal_auth_failure(db, row)
        record_portal_auth_ip_failure(db, ip=ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access code")
    contact = db.get(Contact, row.contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access code")
    # Valid access code is enough to sign in; empty portal home is allowed (soft empty state).
    record_portal_auth_success(db, row)
    token = create_portal_session_token(
        contact_id=str(contact.id),
        session_version=portal_session_version(row),
        audience="client",
    )
    log_event(
        db,
        actor_user_id=None,
        action="portal.auth.success",
        entity_type="contact",
        entity_id=str(contact.id),
        meta={"contact_id": str(contact.id), "audience": "client"},
    )
    db.commit()
    return PortalAuthOut(
        session_token=token,
        contact_name=contact_display_name(contact),
        grants=grant_summaries(db, contact.id),
        staff_preview=False,
        audience="client",
    )


def portal_request_otp(payload: PortalOtpRequestIn, request: Request, db: Session) -> None:
    """Send a one-time sign-in code if this e-mail has active portal access."""
    ip = client_ip_from_request(request)
    email = (payload.email or "").strip().lower()
    check_portal_otp_request_rate_limits(db, email=email, ip=ip)
    record_portal_otp_request_attempt(db, email=email, ip=ip)
    contact = find_portal_contact_by_email(db, payload.email)
    if contact is None:
        return
    code = issue_portal_login_otp(db, contact.id)
    db.commit()
    dispatch_alert(
        db,
        AlertKind.portal_login_otp,
        to_email=contact.email or "",
        context={
            "contact_name": contact_display_name(contact),
            "otp_code": code,
            "portal_url": portal_public_url(),
        },
    )


def portal_verify_otp(payload: PortalOtpVerifyIn, request: Request, db: Session) -> PortalAuthOut:
    ip = client_ip_from_request(request)
    email = (payload.email or "").strip().lower()
    check_portal_otp_verify_rate_limits(db, email=email, ip=ip)
    contact = find_portal_contact_by_email(db, payload.email)
    if contact is None or not verify_portal_login_otp(db, contact.id, payload.code.strip()):
        record_portal_otp_verify_failure(db, email=email, ip=ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired sign-in code")
    clear_portal_otp_verify_rate_limits(db, email=email)
    # Valid OTP + active portal access is enough; empty portal home is allowed.
    access_row = db.execute(
        select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact.id)
    ).scalar_one_or_none()
    if access_row:
        record_portal_auth_success(db, access_row)
    token = create_portal_session_token(
        contact_id=str(contact.id),
        session_version=portal_session_version(access_row),
    )
    log_event(
        db,
        actor_user_id=None,
        action="portal.auth.otp",
        entity_type="contact",
        entity_id=str(contact.id),
        meta={"contact_id": str(contact.id)},
    )
    db.commit()
    return PortalAuthOut(
        session_token=token,
        contact_name=contact_display_name(contact),
        grants=grant_summaries(db, contact.id),
        audience="client",
    )


def portal_preview_exchange(payload: PortalPreviewExchangeIn, db: Session) -> PortalAuthOut:
    """Exchange a short-lived staff-issued preview token for a client portal session."""
    try:
        preview = decode_portal_preview_exchange_token(payload.exchange_token.strip())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    try:
        contact_id = uuid.UUID(preview.contact_id)
        case_id = uuid.UUID(preview.case_id)
        staff_user_id = uuid.UUID(preview.staff_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid preview link") from exc

    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid preview link")
    access_row = db.execute(
        select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact_id)
    ).scalar_one_or_none()
    if access_row is None or not portal_access_is_active(access_row):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Portal access is not active for this contact")

    require_case_portal_enabled(db, case_id)
    if not contact_has_portal_content_on_case(db, contact_id=contact_id, case_id=case_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No portal content on this matter for this contact",
        )
    token = create_portal_session_token(
        contact_id=str(contact.id),
        staff_preview=True,
        session_version=portal_session_version(access_row),
    )
    log_event(
        db,
        actor_user_id=staff_user_id,
        action="portal.preview.exchange",
        entity_type="contact",
        entity_id=str(contact.id),
        meta={"case_id": str(case_id), "contact_id": str(contact.id)},
    )
    db.commit()
    return PortalAuthOut(
        session_token=token,
        contact_name=contact_display_name(contact),
        grants=grant_summaries(db, contact.id),
        focus_case_id=case_id,
        staff_preview=True,
        audience="client",
    )


def portal_quote_exchange(payload: PortalQuoteExchangeIn, db: Session) -> PortalQuoteExchangeOut:
    """Exchange a quote e-mail link for a portal session and quote details."""
    try:
        delivery = resolve_quote_exchange_delivery(db, payload.exchange_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired quote link") from exc

    contact_id = delivery.contact_id
    case_id = delivery.case_id

    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid quote link")
    access_row = db.execute(
        select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact_id)
    ).scalar_one_or_none()
    if access_row is None or not portal_access_is_active(access_row):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Portal access is not active")

    require_case_portal_enabled(db, case_id)

    token = create_portal_session_token(
        contact_id=str(contact.id),
        session_version=portal_session_version(access_row),
    )
    log_event(
        db,
        actor_user_id=None,
        action="portal.quote.exchange",
        entity_type="quote_portal_delivery",
        entity_id=str(delivery.id),
        meta={"case_id": str(case_id), "file_id": str(delivery.file_id), "contact_id": str(contact_id)},
    )
    db.commit()
    return PortalQuoteExchangeOut(
        session_token=token,
        contact_name=contact_display_name(contact),
        grants=grant_summaries(db, contact.id),
        quote=quote_delivery_view(db, delivery),
    )


def portal_form_exchange(payload: PortalFormExchangeIn, db: Session) -> PortalFormExchangeOut:
    """Exchange a form e-mail link for a portal session and open the pending form."""
    try:
        submission = resolve_form_exchange_submission(db, payload.exchange_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired form link") from exc

    contact_id = submission.contact_id
    case_id = submission.case_id

    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid form link")
    access_row = db.execute(
        select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact_id)
    ).scalar_one_or_none()
    if access_row is None or not portal_access_is_active(access_row):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Portal access is not active")

    require_case_portal_enabled(db, case_id)

    token = create_portal_session_token(
        contact_id=str(contact.id),
        session_version=portal_session_version(access_row),
    )
    log_event(
        db,
        actor_user_id=None,
        action="portal.form.exchange",
        entity_type="portal_form_submission",
        entity_id=str(submission.id),
        meta={"case_id": str(case_id), "template_id": str(submission.template_id), "contact_id": str(contact_id)},
    )
    db.commit()
    return PortalFormExchangeOut(
        session_token=token,
        contact_name=contact_display_name(contact),
        grants=grant_summaries(db, contact.id),
        form=form_pending_out(db, submission),
    )


def portal_canary_sign_exchange(payload: PortalCanarySignExchangeIn, db: Session) -> PortalCanarySignExchangeOut:
    """Exchange a Canary Sign e-mail link token for a portal session and signing view."""
    recipient = get_canary_recipient_by_sign_token(db, payload.sign_token)
    if recipient is None or not recipient.contact_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired signing link")
    req = db.get(CanarySignRequest, recipient.signing_request_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired signing link")

    contact = db.get(Contact, recipient.contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signing link")
    access_row = db.execute(
        select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact.id)
    ).scalar_one_or_none()
    if access_row is None or not portal_access_is_active(access_row):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Portal access is not active")

    require_case_portal_enabled(db, req.case_id)

    token = create_portal_session_token(
        contact_id=str(contact.id),
        session_version=portal_session_version(access_row),
    )
    log_event(
        db,
        actor_user_id=None,
        action="portal.canary_sign.exchange",
        entity_type="canary_sign_request",
        entity_id=str(req.id),
        meta={"case_id": str(req.case_id), "contact_id": str(contact.id)},
    )
    db.commit()
    view = canary_portal_signing_view(db, req, recipient=recipient)
    return PortalCanarySignExchangeOut(
        session_token=token,
        contact_name=contact_display_name(contact),
        grants=grant_summaries(db, contact.id),
        signing=PortalCanarySignOut(**view),
    )
