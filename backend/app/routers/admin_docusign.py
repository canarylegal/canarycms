"""Admin: DocuSign integration settings and template listing."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin
from app.docusign_client import DocusignApiError, get_template_roles, list_templates
from app.docusign_settings import docusign_configured, docusign_rsa_private_key, get_docusign_settings
from app.email_crypt import encrypt_password
from app.models import User
from app.schemas import DocusignIntegrationSettingsOut, DocusignIntegrationSettingsUpdate, DocusignTemplateOut

router = APIRouter(prefix="/admin/docusign", tags=["admin-docusign"])

log = logging.getLogger(__name__)


def _row_to_out(row) -> DocusignIntegrationSettingsOut:
    return DocusignIntegrationSettingsOut(
        enabled=bool(row.enabled),
        use_demo=bool(row.use_demo),
        allow_tier_a=bool(row.allow_tier_a),
        allow_tier_b=bool(row.allow_tier_b),
        allow_tier_c=bool(row.allow_tier_c),
        allow_wes=bool(row.allow_wes),
        allow_qes=bool(row.allow_qes),
        account_id=(row.account_id or "").strip() or None,
        integration_key=(row.integration_key or "").strip() or None,
        user_id=(row.user_id or "").strip() or None,
        rsa_private_key_configured=bool((row.rsa_private_key_enc or "").strip()),
        connect_hmac_secret_configured=bool((row.connect_hmac_secret_enc or "").strip()),
        api_base_uri=(row.api_base_uri or "").strip() or None,
        cost_standard_pence=row.cost_standard_pence,
        cost_wes_pence=row.cost_wes_pence,
        cost_qes_pence=row.cost_qes_pence,
        configured=False,
    )


@router.get("/settings", response_model=DocusignIntegrationSettingsOut)
def get_docusign_settings_route(_admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> DocusignIntegrationSettingsOut:
    row = get_docusign_settings(db)
    out = _row_to_out(row)
    return out.model_copy(update={"configured": docusign_configured(db)})


@router.put("/settings", response_model=DocusignIntegrationSettingsOut)
def put_docusign_settings(
    payload: DocusignIntegrationSettingsUpdate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DocusignIntegrationSettingsOut:
    row = get_docusign_settings(db)
    data = payload.model_dump(exclude_unset=True)
    for key in (
        "enabled",
        "use_demo",
        "allow_tier_a",
        "allow_tier_b",
        "allow_tier_c",
        "allow_wes",
        "allow_qes",
    ):
        if key in data and data[key] is not None:
            setattr(row, key, bool(data[key]))
    for key in ("account_id", "integration_key", "user_id", "api_base_uri"):
        if key in data:
            val = (data[key] or "").strip()
            setattr(row, key, val if val else None)
    if "rsa_private_key" in data:
        val = (data["rsa_private_key"] or "").strip()
        row.rsa_private_key_enc = encrypt_password(val) if val else None
    if "connect_hmac_secret" in data:
        val = (data["connect_hmac_secret"] or "").strip()
        row.connect_hmac_secret_enc = encrypt_password(val) if val else None
    for key in ("cost_standard_pence", "cost_wes_pence", "cost_qes_pence"):
        if key in data:
            val = data[key]
            setattr(row, key, int(val) if val is not None and int(val) > 0 else None)
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    db.refresh(row)
    out = _row_to_out(row)
    return out.model_copy(update={"configured": docusign_configured(db)})


@router.get("/templates", response_model=list[DocusignTemplateOut])
def list_docusign_templates(_admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[DocusignTemplateOut]:
    row = get_docusign_settings(db)
    if not docusign_configured(db):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="DocuSign is not configured")
    try:
        private_key = docusign_rsa_private_key(row)
        templates = list_templates(row, private_key_pem=private_key)
    except RuntimeError as e:
        log.warning("DocuSign template list failed (admin config): %s", e)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    except DocusignApiError as e:
        log.warning("DocuSign template list failed (admin): %s", e)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    out: list[DocusignTemplateOut] = []
    for t in templates:
        roles: list[str] = []
        try:
            role_rows = get_template_roles(row, private_key_pem=private_key, template_id=t.template_id)
            roles = [r.role_name for r in role_rows]
        except DocusignApiError:
            pass
        out.append(
            DocusignTemplateOut(
                template_id=t.template_id,
                name=t.name,
                description=t.description,
                roles=roles,
            )
        )
    return out
