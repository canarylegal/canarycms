"""Core shim — DocuSign signing service (commercial package when attached)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.commercial_runtime import reexport_commercial

if not reexport_commercial(globals(), "canary_commercial.docusign_signing_service"):

    def list_pending_for_contact(db: Session, *args, **kwargs) -> list:  # type: ignore[no-redef]
        return []

    def portal_signing_view(*args, **kwargs):  # type: ignore[no-redef]
        return None

    def sync_envelope_status(*args, **kwargs):  # type: ignore[no-redef]
        return None

    def sync_pending_signing_requests(db: Session, *args, **kwargs) -> None:  # type: ignore[no-redef]
        return None

    def signing_request_file_list_item(sr) -> dict[str, Any]:  # type: ignore[no-redef]
        return {}

    def get_recipient_by_sign_token(db: Session, token: str):  # type: ignore[no-redef]
        return None

    def create_signing_redirect_url(*args, **kwargs):  # type: ignore[no-redef]
        raise RuntimeError("DocuSign is not available (commercial package not attached)")

    def send_signing_request(*args, **kwargs):  # type: ignore[no-redef]
        raise RuntimeError("DocuSign is not available (commercial package not attached)")

    def resend_signing_notifications(*args, **kwargs):  # type: ignore[no-redef]
        raise RuntimeError("DocuSign is not available (commercial package not attached)")

    def void_signing_request(*args, **kwargs):  # type: ignore[no-redef]
        raise RuntimeError("DocuSign is not available (commercial package not attached)")

    def active_signing_for_file(*args, **kwargs):  # type: ignore[no-redef]
        return None

    def list_signing_menu_rows(*args, **kwargs) -> list:  # type: ignore[no-redef]
        return []

    def signing_request_out(*args, **kwargs):  # type: ignore[no-redef]
        return None
