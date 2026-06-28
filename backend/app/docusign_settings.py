"""Load singleton DocuSign integration settings."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.email_crypt import decrypt_password
from app.models import DocusignIntegrationSettings


def get_docusign_settings(db: Session) -> DocusignIntegrationSettings:
    row = db.get(DocusignIntegrationSettings, 1)
    if row is None:
        raise RuntimeError(
            "docusign_integration_settings row missing — run database migrations (alembic upgrade head).",
        )
    return row


def docusign_configured(db: Session) -> bool:
    row = get_docusign_settings(db)
    if not row.enabled:
        return False
    return bool(
        (row.account_id or "").strip()
        and (row.integration_key or "").strip()
        and (row.user_id or "").strip()
        and (row.rsa_private_key_enc or "").strip()
    )


def docusign_rsa_private_key(row: DocusignIntegrationSettings) -> str:
    enc = (row.rsa_private_key_enc or "").strip()
    if not enc:
        raise RuntimeError("DocuSign RSA private key is not configured")
    try:
        return decrypt_password(enc)
    except Exception as e:
        raise RuntimeError(
            "DocuSign RSA private key could not be decrypted — re-enter it in Admin → DocuSign "
            "(do not copy encrypted values from another server)."
        ) from e


def docusign_connect_hmac_secret(row: DocusignIntegrationSettings) -> str | None:
    enc = (row.connect_hmac_secret_enc or "").strip()
    if not enc:
        return None
    return decrypt_password(enc)


def envelope_cost_pence(row: DocusignIntegrationSettings, level) -> int:
    """Configured forecast cost for a send; 0 when not set."""
    from app.models import DocusignSignatureLevel

    if level == DocusignSignatureLevel.wes:
        raw = row.cost_wes_pence
    elif level == DocusignSignatureLevel.qes:
        raw = row.cost_qes_pence
    else:
        raw = row.cost_standard_pence
    if raw is None or raw <= 0:
        return 0
    return int(raw)
