"""DocuSign REST API client (JWT grant)."""

from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from app.models import DocusignIntegrationSettings

log = logging.getLogger(__name__)

_TOKEN_CACHE: dict[str, tuple[str, float, str]] = {}


@dataclass(frozen=True)
class DocusignTemplateSummary:
    template_id: str
    name: str
    description: str | None


@dataclass(frozen=True)
class DocusignTemplateRole:
    role_name: str
    routing_order: str | None


class DocusignApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, detail: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


def _auth_host(use_demo: bool) -> str:
    return "account-d.docusign.com" if use_demo else "account.docusign.com"


def _default_api_base(use_demo: bool) -> str:
    return "https://demo.docusign.net/restapi" if use_demo else "https://na1.docusign.net/restapi"


def _cache_key(row: DocusignIntegrationSettings) -> str:
    return f"{row.integration_key}:{row.user_id}:{row.use_demo}"


def _request_access_token(row: DocusignIntegrationSettings, *, private_key_pem: str) -> tuple[str, str]:
    integration_key = (row.integration_key or "").strip()
    user_id = (row.user_id or "").strip()
    auth_host = _auth_host(bool(row.use_demo))
    now = int(time.time())
    try:
        assertion = jwt.encode(
            {
                "iss": integration_key,
                "sub": user_id,
                "aud": auth_host,
                "iat": now,
                "exp": now + 3600,
                "scope": "signature impersonation",
            },
            private_key_pem,
            algorithm="RS256",
        )
    except Exception as e:
        raise DocusignApiError(
            "DocuSign RSA private key is invalid — paste the full PEM from DocuSign Admin → Apps and Keys."
        ) from e
    url = f"https://{auth_host}/oauth/token"
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            url,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
        )
    if resp.status_code >= 400:
        msg = f"DocuSign authentication failed ({resp.status_code})"
        try:
            err = resp.json()
            if err.get("error") == "consent_required":
                ik = integration_key
                host = auth_host
                consent = (
                    f"https://{host}/oauth/auth?response_type=code&scope=signature%20impersonation"
                    f"&client_id={ik}&redirect_uri=https://developers.docusign.com/platform/auth/consent"
                )
                msg += f". JWT consent is required for the API sender — grant access once: {consent}"
            elif err.get("error_description"):
                desc = str(err["error_description"])
                msg += f": {desc}"
                if "issuer_not_found" in desc.lower():
                    msg += (
                        ". Your integration key is not registered in this DocuSign environment — "
                        "if the key is from the developer/demo account, enable “Use DocuSign demo environment” "
                        "in Admin → DocuSign; production keys require that box unticked."
                    )
            elif err.get("message"):
                msg += f": {err['message']}"
        except Exception:
            snippet = (resp.text or "").strip()
            if snippet:
                msg += f": {snippet[:240]}"
        raise DocusignApiError(msg, status_code=resp.status_code, detail=resp.text)
    data = resp.json()
    access_token = str(data.get("access_token") or "")
    if not access_token:
        raise DocusignApiError("DocuSign authentication returned no access token")
    base_uri = (row.api_base_uri or "").strip().rstrip("/")
    if not base_uri:
        base_uri = _resolve_base_uri(access_token, auth_host, bool(row.use_demo))
    if not base_uri.endswith("/restapi"):
        base_uri = base_uri.rstrip("/") + "/restapi"
    return access_token, base_uri


def _resolve_userinfo_accounts(access_token: str, auth_host: str) -> list[dict[str, Any]]:
    url = f"https://{auth_host}/oauth/userinfo"
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, headers={"Authorization": f"Bearer {access_token}"})
    if resp.status_code >= 400:
        return []
    data = resp.json()
    accounts = data.get("accounts") or []
    return [a for a in accounts if isinstance(a, dict)]


def _resolve_base_uri(access_token: str, auth_host: str, use_demo: bool) -> str:
    accounts = _resolve_userinfo_accounts(access_token, auth_host)
    if not accounts:
        return _default_api_base(use_demo)
    base_uri = str(accounts[0].get("base_uri") or "").strip()
    return base_uri or _default_api_base(use_demo)


def _resolve_account_id(access_token: str, auth_host: str) -> str:
    accounts = _resolve_userinfo_accounts(access_token, auth_host)
    for acct in accounts:
        if acct.get("is_default"):
            return str(acct.get("account_id") or "").strip()
    if accounts:
        return str(accounts[0].get("account_id") or "").strip()
    return ""


def _effective_account_id(
    row: DocusignIntegrationSettings,
    *,
    access_token: str,
    auth_host: str,
) -> str:
    account_id = (row.account_id or "").strip()
    # DocuSign API account IDs are GUIDs; numeric values are display account numbers.
    if account_id and not account_id.isdigit():
        return account_id
    resolved = _resolve_account_id(access_token, auth_host)
    if resolved:
        if account_id:
            log.info(
                "DocuSign account_id %s looks like a display number; using API account %s",
                account_id,
                resolved,
            )
        return resolved
    if account_id:
        return account_id
    raise DocusignApiError("DocuSign account ID is not configured")


def get_access_token(row: DocusignIntegrationSettings, *, private_key_pem: str) -> tuple[str, str]:
    key = _cache_key(row)
    cached = _TOKEN_CACHE.get(key)
    now = time.time()
    if cached and cached[1] > now + 60:
        return cached[0], cached[2]
    token, base_uri = _request_access_token(row, private_key_pem=private_key_pem)
    _TOKEN_CACHE[key] = (token, now + 3500, base_uri)
    return token, base_uri


def _api_request(
    row: DocusignIntegrationSettings,
    *,
    private_key_pem: str,
    method: str,
    path: str,
    json_body: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
) -> Any:
    token, base_uri = get_access_token(row, private_key_pem=private_key_pem)
    auth_host = _auth_host(bool(row.use_demo))
    account_id = _effective_account_id(row, access_token=token, auth_host=auth_host)
    url = f"{base_uri}/v2.1/accounts/{account_id}{path}"
    with httpx.Client(timeout=60.0) as client:
        resp = client.request(
            method,
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=json_body,
            params=params,
        )
    if resp.status_code >= 400:
        detail: Any = resp.text
        try:
            detail = resp.json()
        except Exception:
            pass
        msg = f"DocuSign API error ({resp.status_code})"
        if isinstance(detail, dict):
            code = detail.get("errorCode") or detail.get("error")
            message = detail.get("message") or detail.get("error_description")
            if code:
                msg += f": {code}"
            if message:
                msg += f" — {message}"
        elif isinstance(detail, str) and detail.strip():
            msg += f": {detail.strip()[:240]}"
        raise DocusignApiError(msg, status_code=resp.status_code, detail=detail)
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()


def list_templates(row: DocusignIntegrationSettings, *, private_key_pem: str) -> list[DocusignTemplateSummary]:
    data = _api_request(
        row,
        private_key_pem=private_key_pem,
        method="GET",
        path="/templates",
        params={"count": "100"},
    )
    out: list[DocusignTemplateSummary] = []
    for item in (data or {}).get("envelopeTemplates") or []:
        tid = str(item.get("templateId") or "").strip()
        if not tid:
            continue
        out.append(
            DocusignTemplateSummary(
                template_id=tid,
                name=str(item.get("name") or "Template"),
                description=(str(item.get("description")).strip() if item.get("description") else None),
            )
        )
    return out


def get_template_roles(
    row: DocusignIntegrationSettings,
    *,
    private_key_pem: str,
    template_id: str,
) -> list[DocusignTemplateRole]:
    data = _api_request(
        row,
        private_key_pem=private_key_pem,
        method="GET",
        path=f"/templates/{template_id}/recipients",
    )
    roles: list[DocusignTemplateRole] = []
    for signer in (data or {}).get("signers") or []:
        role_name = str(signer.get("roleName") or "").strip()
        if not role_name:
            continue
        roles.append(
            DocusignTemplateRole(
                role_name=role_name,
                routing_order=str(signer.get("routingOrder") or "") or None,
            )
        )
    return roles


def create_envelope(
    row: DocusignIntegrationSettings,
    *,
    private_key_pem: str,
    body: dict[str, Any],
) -> str:
    data = _api_request(row, private_key_pem=private_key_pem, method="POST", path="/envelopes", json_body=body)
    envelope_id = str((data or {}).get("envelopeId") or "").strip()
    if not envelope_id:
        raise DocusignApiError("DocuSign did not return an envelope ID")
    return envelope_id


def get_document_page_count(
    row: DocusignIntegrationSettings,
    *,
    private_key_pem: str,
    envelope_id: str,
    document_id: str = "1",
) -> int:
    """Return page count after DocuSign has ingested a draft envelope document."""
    data = _api_request(
        row,
        private_key_pem=private_key_pem,
        method="GET",
        path=f"/envelopes/{envelope_id}/documents/{document_id}/pages",
    )
    pages = (data or {}).get("pages") if isinstance(data, dict) else None
    if isinstance(pages, list) and pages:
        return len(pages)
    return 1


def create_recipient_tabs(
    row: DocusignIntegrationSettings,
    *,
    private_key_pem: str,
    envelope_id: str,
    recipient_id: str,
    tabs: dict[str, Any],
) -> None:
    _api_request(
        row,
        private_key_pem=private_key_pem,
        method="POST",
        path=f"/envelopes/{envelope_id}/recipients/{recipient_id}/tabs",
        json_body=tabs,
    )


def send_envelope(
    row: DocusignIntegrationSettings,
    *,
    private_key_pem: str,
    envelope_id: str,
) -> None:
    _api_request(
        row,
        private_key_pem=private_key_pem,
        method="PUT",
        path=f"/envelopes/{envelope_id}",
        json_body={"status": "sent"},
    )


def create_recipient_view(
    row: DocusignIntegrationSettings,
    *,
    private_key_pem: str,
    envelope_id: str,
    body: dict[str, Any],
) -> str:
    data = _api_request(
        row,
        private_key_pem=private_key_pem,
        method="POST",
        path=f"/envelopes/{envelope_id}/views/recipient",
        json_body=body,
    )
    url = str((data or {}).get("url") or "").strip()
    if not url:
        raise DocusignApiError("DocuSign did not return a signing URL")
    return url


def void_envelope(
    row: DocusignIntegrationSettings,
    *,
    private_key_pem: str,
    envelope_id: str,
    reason: str,
) -> None:
    _api_request(
        row,
        private_key_pem=private_key_pem,
        method="PUT",
        path=f"/envelopes/{envelope_id}",
        json_body={"status": "voided", "voidedReason": reason[:200]},
    )


def get_envelope(
    row: DocusignIntegrationSettings,
    *,
    private_key_pem: str,
    envelope_id: str,
) -> dict[str, Any]:
    data = _api_request(
        row,
        private_key_pem=private_key_pem,
        method="GET",
        path=f"/envelopes/{envelope_id}",
    )
    return data or {}


def download_envelope_document_bytes(
    row: DocusignIntegrationSettings,
    *,
    private_key_pem: str,
    envelope_id: str,
    document_id: str = "combined",
) -> bytes:
    token, base_uri = get_access_token(row, private_key_pem=private_key_pem)
    auth_host = _auth_host(bool(row.use_demo))
    account_id = _effective_account_id(row, access_token=token, auth_host=auth_host)
    url = f"{base_uri}/v2.1/accounts/{account_id}/envelopes/{envelope_id}/documents/{document_id}"
    with httpx.Client(timeout=120.0) as client:
        resp = client.get(url, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code >= 400:
        raise DocusignApiError(
            f"DocuSign document download failed ({resp.status_code})",
            status_code=resp.status_code,
            detail=resp.text,
        )
    return resp.content


def file_extension_for_mime(mime_type: str, filename: str) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return "pdf"
    if name.endswith(".docx"):
        return "docx"
    if name.endswith(".doc"):
        return "doc"
    mt = (mime_type or "").lower()
    if "pdf" in mt:
        return "pdf"
    if "wordprocessingml" in mt or "msword" in mt:
        return "docx"
    return "pdf"


def encode_document_base64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")
