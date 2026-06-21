"""Case-scoped portal form send and submission tracking."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alert_dispatch import firm_alerts_configured
from app.db import get_db
from app.deps import get_current_user, require_case_access
from app.models import PortalFormSubmission, User
from app.portal_case import require_case_portal_enabled
from app.portal_form_service import (
    list_templates_for_case,
    send_form_to_contact,
    submission_out,
    template_out,
    void_submission,
)
from app.schemas import (
    PortalFormSendIn,
    PortalFormSubmissionOut,
    PortalFormTemplateOut,
    QuotePortalSendPreflightOut,
)

router = APIRouter(prefix="/cases/{case_id}/portal/forms", tags=["case-portal-forms"])


def _require_portal(case_id: uuid.UUID, user: User, db: Session) -> None:
    require_case_access(case_id, user, db)
    require_case_portal_enabled(db, case_id)


@router.get("/send-preflight", response_model=QuotePortalSendPreflightOut)
def form_send_preflight(
    case_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuotePortalSendPreflightOut:
    _require_portal(case_id, user, db)
    return QuotePortalSendPreflightOut(alerts_configured=firm_alerts_configured(db))


@router.get("/templates", response_model=list[PortalFormTemplateOut])
def case_form_templates(
    case_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PortalFormTemplateOut]:
    _require_portal(case_id, user, db)
    rows = list_templates_for_case(db, case_id)
    return [PortalFormTemplateOut.model_validate(template_out(db, t)) for t in rows]


@router.get("/submissions", response_model=list[PortalFormSubmissionOut])
def case_form_submissions(
    case_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PortalFormSubmissionOut]:
    _require_portal(case_id, user, db)
    rows = (
        db.execute(
            select(PortalFormSubmission)
            .where(PortalFormSubmission.case_id == case_id)
            .order_by(PortalFormSubmission.sent_at.desc())
        )
        .scalars()
        .all()
    )
    return [PortalFormSubmissionOut.model_validate(submission_out(db, r)) for r in rows]


@router.post("/send", response_model=PortalFormSubmissionOut, status_code=status.HTTP_201_CREATED)
def send_form(
    case_id: uuid.UUID,
    payload: PortalFormSendIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortalFormSubmissionOut:
    _require_portal(case_id, user, db)
    row, email_sent, skip_reason = send_form_to_contact(
        db,
        case_id=case_id,
        template_id=payload.template_id,
        contact_id=payload.contact_id,
        actor=user,
    )
    db.commit()
    db.refresh(row)
    out = submission_out(db, row)
    out["email_sent"] = email_sent
    out["email_skip_reason"] = skip_reason
    return PortalFormSubmissionOut.model_validate(out)


@router.post("/submissions/{submission_id}/void", response_model=PortalFormSubmissionOut)
def void_form_submission(
    case_id: uuid.UUID,
    submission_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortalFormSubmissionOut:
    _require_portal(case_id, user, db)
    row = db.get(PortalFormSubmission, submission_id)
    if row is None or row.case_id != case_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Submission not found")
    void_submission(db, submission=row, actor=user)
    db.commit()
    db.refresh(row)
    return PortalFormSubmissionOut.model_validate(submission_out(db, row))
