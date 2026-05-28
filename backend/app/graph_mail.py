"""Microsoft Graph: create Outlook drafts (application permissions + admin consent)."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from urllib.parse import quote, urlparse

import httpx
from sqlalchemy.orm import Session

from app.owa_urls import (
    build_owa_compose_deeplink_from_graph_weblink,
    build_owa_compose_prefill_url,
    build_owa_compose_with_graph_attachments,
    build_owa_open_graph_draft_compose_urls,
)

log = logging.getLogger(__name__)


def graph_mail_configured(db: Session | None = None) -> bool:
    """True when Entra credentials resolve and admin has not forced mailto-only mode."""
    if db is None:
        return bool(
            (os.getenv("CANARY_MS_GRAPH_TENANT_ID") or "").strip()
            and (os.getenv("CANARY_MS_GRAPH_CLIENT_ID") or "").strip()
            and (os.getenv("CANARY_MS_GRAPH_CLIENT_SECRET") or "").strip()
        )
    from app.email_integration_settings import graph_mail_effective_configured

    return graph_mail_effective_configured(db)


def _resolve_creds(db: Session | None) -> tuple[str, str, str]:
    if db is None:
        t = (os.getenv("CANARY_MS_GRAPH_TENANT_ID") or "").strip()
        c = (os.getenv("CANARY_MS_GRAPH_CLIENT_ID") or "").strip()
        s = (os.getenv("CANARY_MS_GRAPH_CLIENT_SECRET") or "").strip()
        if not (t and c and s):
            raise RuntimeError("Microsoft Graph credentials are not configured.")
        return (t, c, s)
    from app.email_integration_settings import effective_graph_credentials

    creds = effective_graph_credentials(db)
    if not creds:
        raise RuntimeError("Microsoft Graph credentials are not configured for this deployment.")
    return creds


def app_access_token(db: Session | None = None) -> str:
    tenant, client_id, client_secret = _resolve_creds(db)
    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
        "scope": "https://graph.microsoft.com/.default",
    }
    try:
        with httpx.Client(timeout=25.0) as client:
            res = client.post(token_url, data=payload)
    except httpx.RequestError as e:
        raise RuntimeError(f"Could not reach Microsoft login to obtain a Graph token: {e}") from e
    if res.status_code >= 400:
        txt = (res.text or "").strip()
        raise RuntimeError(f"Microsoft Graph token request failed ({res.status_code}): {txt[:700]}")
    try:
        token_body = res.json()
    except json.JSONDecodeError:
        raise RuntimeError(
            f"Microsoft Graph token response was not JSON ({res.status_code}): {(res.text or '')[:500]}",
        ) from None
    tok = token_body.get("access_token")
    if not isinstance(tok, str) or not tok.strip():
        raise RuntimeError("Microsoft Graph token response did not include access_token.")
    return tok


def _owa_mail_base_for_compose_deeplinks(db: Session | None = None, user: object | None = None) -> str:
    if db is None:
        raw = (os.getenv("CANARY_OUTLOOK_WEB_MAIL_BASE") or "https://outlook.office.com/mail").strip().rstrip("/")
    else:
        from app.email_integration_settings import (
            effective_outlook_web_mail_base,
            effective_outlook_web_mail_base_for_user,
        )
        from app.models import User

        if user is not None and isinstance(user, User):
            raw = effective_outlook_web_mail_base_for_user(db, user)
        else:
            raw = effective_outlook_web_mail_base(db)
    try:
        host = (urlparse(raw if "://" in raw else f"https://{raw}").hostname or "").lower()
    except Exception:
        host = ""
    if host == "outlook.office365.com":
        return "https://outlook.office.com/mail"
    return raw


def _normalize_outlook_office365_web_link_to_office_com(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return u
    return re.sub(
        r"^https?://outlook\.office365\.com(?=/|$)",
        "https://outlook.office.com",
        u,
        count=1,
        flags=re.IGNORECASE,
    )


def outlook_category_names() -> list[str]:
    raw = (os.getenv("CANARY_OUTLOOK_CATEGORY_NAME") or "Canary").strip()
    return [raw] if raw else []


def _graph_attach_files(
    client: httpx.Client,
    *,
    mailbox: str,
    draft_id: str,
    token: str,
    attachments: list[tuple[str, str, bytes]],
) -> None:
    att_base = (
        f"https://graph.microsoft.com/v1.0/users/{quote(mailbox)}"
        f"/messages/{quote(draft_id, safe='')}/attachments"
    )
    att_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    for fname, mime, content in attachments:
        att_payload = {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": fname,
            "contentType": mime or "application/octet-stream",
            "contentBytes": base64.b64encode(content).decode("ascii"),
        }
        att_res = client.post(att_base, headers=att_headers, json=att_payload)
        if att_res.status_code >= 400:
            txt = (att_res.text or "").strip()
            raise RuntimeError(
                f"Microsoft Graph attachment upload failed ({att_res.status_code}) "
                f"for {fname}: {txt[:600]}",
            )


def _graph_refresh_draft(
    client: httpx.Client,
    *,
    mailbox: str,
    draft_id: str,
    token: str,
) -> dict:
    get_res = client.get(
        f"https://graph.microsoft.com/v1.0/users/{quote(mailbox)}"
        f"/messages/{quote(draft_id, safe='')}"
        "?$select=id,webLink,hasAttachments,subject,body,toRecipients,internetMessageId",
        headers={"Authorization": f"Bearer {token}"},
    )
    if get_res.status_code >= 400:
        log.warning(
            "Could not refresh Graph draft after create (%s): %s",
            get_res.status_code,
            (get_res.text or "")[:300],
        )
        return {"id": draft_id}
    try:
        refreshed = get_res.json()
    except json.JSONDecodeError:
        return {"id": draft_id}
    if isinstance(refreshed, dict) and refreshed.get("id"):
        return refreshed
    return {"id": draft_id}


def create_outlook_draft(
    mailbox_user: str,
    *,
    to_addr: str,
    subject: str,
    body_text: str,
    attachments: list[tuple[str, str, bytes]],
    db: Session | None = None,
    mailbox_user_row: object | None = None,
) -> tuple[str, str | None, str | None, str | None, str | None]:
    """
    Create a draft via Graph (when attachments present) or OWA prefill-only (no attachments).

    Returns
    (open_url, graph_message_id, compose_fallback_url, internet_message_id, compose_prefill_url).
    """
    mailbox = mailbox_user.strip()
    if not mailbox:
        raise RuntimeError("Mailbox user principal name is required.")

    owa_base = _owa_mail_base_for_compose_deeplinks(db, mailbox_user_row)
    has_attachments = bool(attachments)

    if not has_attachments:
        prefill = build_owa_compose_prefill_url(
            owa_base,
            to=to_addr,
            subject=subject,
            body=body_text,
        )
        return prefill, None, None, None, prefill

    token = app_access_token(db)

    cats = outlook_category_names()
    msg: dict = {
        "subject": (subject or "").strip() or "Draft",
        "isDraft": True,
        "body": {
            "contentType": "Text",
            "content": (body_text or "").strip(),
        },
    }
    if cats:
        msg["categories"] = cats
    to_clean = (to_addr or "").strip()
    if to_clean:
        msg["toRecipients"] = [{"emailAddress": {"address": to_clean}}]

    url = f"https://graph.microsoft.com/v1.0/users/{quote(mailbox)}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=90.0) as client:
            res = client.post(url, headers=headers, json=msg)
            if res.status_code >= 400:
                txt = (res.text or "").strip()
                raise RuntimeError(f"Microsoft Graph draft create failed ({res.status_code}): {txt[:1200]}")
            try:
                body = res.json()
            except json.JSONDecodeError:
                raise RuntimeError(
                    f"Microsoft Graph returned a non-JSON body after creating the draft ({res.status_code}): "
                    f"{(res.text or '')[:800]}",
                ) from None
            draft_id = body.get("id")
            if not isinstance(draft_id, str) or not draft_id.strip():
                raise RuntimeError("Microsoft Graph created the draft but did not return an id.")
            draft_id = draft_id.strip()

            if attachments:
                _graph_attach_files(
                    client,
                    mailbox=mailbox,
                    draft_id=draft_id,
                    token=token,
                    attachments=attachments,
                )
            body = _graph_refresh_draft(client, mailbox=mailbox, draft_id=draft_id, token=token)
            if attachments and not body.get("hasAttachments"):
                log.warning(
                    "Graph draft %s hasAttachments=false after uploading %s file(s)",
                    draft_id[:48],
                    len(attachments),
                )
    except httpx.RequestError as e:
        raise RuntimeError(f"Could not reach Microsoft Graph to create the draft: {e}") from e

    prefill_url = build_owa_compose_prefill_url(
        owa_base,
        to=to_addr,
        subject=subject,
        body=body_text,
    )
    compose_open_url = build_owa_compose_with_graph_attachments(
        body,
        owa_base,
        to=to_addr,
        subject=subject,
        body=body_text,
    )
    draft_item_url = build_owa_compose_deeplink_from_graph_weblink(body, owa_base)
    draft_path_url, draft_query_url = build_owa_open_graph_draft_compose_urls(body, owa_base)
    draft_backup_url = draft_item_url or draft_query_url or draft_path_url
    imid_raw = body.get("internetMessageId")
    internet_message_id = imid_raw.strip() if isinstance(imid_raw, str) and imid_raw.strip() else None
    return (
        compose_open_url,
        draft_id,
        draft_backup_url,
        internet_message_id,
        prefill_url,
    )
