"""Optional commercial enrichment for Core portal / files.

When canary-commercial is attached these call into ``canary_commercial.*``.
When detached they return empty / False / raise so Core-only installs stay safe.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.commercial_runtime import import_commercial


def _docusign_signing():
    return import_commercial("canary_commercial.docusign_signing_service")


def _docusign_settings():
    return import_commercial("canary_commercial.docusign_settings")


def _casera_service():
    return import_commercial("canary_commercial.casera_service")


def list_pending_docusign_for_contact(db: Session, contact_id: uuid.UUID) -> list:
    mod = _docusign_signing()
    if mod is None:
        return []
    return list(mod.list_pending_for_contact(db, contact_id))


def docusign_portal_signing_view(db: Session, req: Any, **kwargs: Any) -> dict[str, Any] | None:
    mod = _docusign_signing()
    if mod is None:
        return None
    return mod.portal_signing_view(db, req, **kwargs)


def sync_envelope_status(db: Session, req: Any) -> Any:
    mod = _docusign_signing()
    if mod is None:
        return None
    return mod.sync_envelope_status(db, req)


def get_recipient_by_sign_token(db: Session, token: str) -> Any:
    mod = _docusign_signing()
    if mod is None:
        return None
    return mod.get_recipient_by_sign_token(db, token)


def create_signing_redirect_url(db: Session, recipient: Any) -> str:
    mod = _docusign_signing()
    if mod is None:
        raise RuntimeError("DocuSign is not available (commercial package not attached)")
    return mod.create_signing_redirect_url(db, recipient)


def sync_pending_signing_requests(db: Session, **kwargs: Any) -> None:
    mod = _docusign_signing()
    if mod is None:
        return None
    return mod.sync_pending_signing_requests(db, **kwargs)


def signing_request_file_list_item(sr: Any) -> dict[str, Any]:
    mod = _docusign_signing()
    if mod is None:
        return {}
    return dict(mod.signing_request_file_list_item(sr) or {})


def docusign_enabled(db: Session) -> bool:
    mod = _docusign_settings()
    if mod is None:
        return False
    row = mod.get_docusign_settings(db)
    return bool(getattr(row, "enabled", False))


def search_file_summaries_for_case(db: Session, case_id: uuid.UUID) -> dict:
    mod = _casera_service()
    if mod is None:
        return {}
    return dict(mod.search_file_summaries_for_case(db, case_id) or {})
