"""Core shim — DocuSign settings (commercial package when attached)."""

from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.commercial_runtime import import_commercial, reexport_commercial

if not reexport_commercial(globals(), "canary_commercial.docusign_settings"):

    def get_docusign_settings(db: Session):  # type: ignore[no-redef]
        return SimpleNamespace(enabled=False)

    def docusign_configured(db: Session) -> bool:  # type: ignore[no-redef]
        return False

    def docusign_rsa_private_key(row):  # type: ignore[no-redef]
        raise RuntimeError("DocuSign is not available (commercial package not attached)")

    def docusign_connect_hmac_secret(row):  # type: ignore[no-redef]
        return ""

    def envelope_cost_pence(row, *args, **kwargs) -> int:  # type: ignore[no-redef]
        return 0
