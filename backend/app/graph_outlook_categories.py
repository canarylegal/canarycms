"""Microsoft Graph: ensure Outlook master category list includes the Canary name (app-only).

Used so the Outlook add-in can apply ``item.categories`` without each user creating the
category manually in Outlook first.

**Pros (Canary API + Graph helper)** — server calls Graph to seed each mailbox’s master list;
the add-in still tags the open message via Office.js after a successful file.

- One admin-consented app registration; same env vars as draft mail (``CANARY_MS_GRAPH_*``).
- Idempotent: skips if the category name already exists (case-insensitive).
- No need to store “category applied” in Canary — Outlook keeps that on the message.
- Optional to reduce failures when ``masterCategories.addAsync`` is flaky in the client.

**Cons**

- Requires **Application** permission **MailboxSettings.ReadWrite** (in addition to whatever
  you use for Mail) plus **admin consent** — broad access to mailbox settings per user.
- Canary only provisions for ``mailbox`` when it **matches the signed-in user’s email**
  (prevents arbitrary mailbox targeting).
- If a user’s **Canary login email ≠ their M365 mailbox** (shared mailbox, aliases), this
  path may not apply until those are aligned or the API is extended.
- Extra latency and dependency on Microsoft Graph availability at provision time.

See also: https://learn.microsoft.com/graph/api/outlookuserpost-mastercategories
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

import httpx

from sqlalchemy.orm import Session

from app.graph_mail import (
    _normalize_outlook_office365_web_link_to_office_com,
    app_access_token,
    graph_mail_configured,
    outlook_category_names,
)

log = logging.getLogger(__name__)


def _primary_category_display_name() -> str:
    names = outlook_category_names()
    return (names[0] if names else "Canary").strip() or "Canary"


def _graph_user_master_categories_url(mailbox: str) -> str:
    m = mailbox.strip()
    return f"https://graph.microsoft.com/v1.0/users/{quote(m)}/outlook/masterCategories"


def ensure_master_category_for_mailbox(mailbox: str, db: Session) -> dict[str, Any]:
    """
    Ensure the configured Outlook master category (``CANARY_OUTLOOK_CATEGORY_NAME``) exists
    for ``mailbox`` (UPN or SMTP). Returns a small status dict for the API layer.

    Raises ``RuntimeError`` on Graph misconfiguration or hard failures.
    """
    if not graph_mail_configured(db):
        raise RuntimeError("Microsoft Graph is not configured (set CANARY_MS_GRAPH_*).")

    display = _primary_category_display_name()
    token = app_access_token(db)
    base = _graph_user_master_categories_url(mailbox)
    headers = {"Authorization": f"Bearer {token}"}

    existing: list[dict[str, Any]] = []
    try:
        with httpx.Client(timeout=40.0) as client:
            next_url: str | None = base
            while next_url:
                res = client.get(next_url, headers=headers)
                if res.status_code == 404:
                    raise RuntimeError(
                        "Graph returned 404 for this mailbox — check the user exists in Entra ID "
                        "and the app has MailboxSettings.ReadWrite (application).",
                    )
                if res.status_code >= 400:
                    txt = (res.text or "").strip()
                    raise RuntimeError(f"Graph list masterCategories failed ({res.status_code}): {txt[:900]}")
                data = res.json()
                batch = data.get("value")
                if isinstance(batch, list):
                    existing.extend([x for x in batch if isinstance(x, dict)])
                next_link = data.get("@odata.nextLink")
                next_url = next_link if isinstance(next_link, str) and next_link.strip() else None
    except httpx.RequestError as e:
        raise RuntimeError(f"Could not reach Microsoft Graph: {e}") from e

    for row in existing:
        dn = row.get("displayName")
        if isinstance(dn, str) and dn.strip().lower() == display.lower():
            return {"status": "already_present", "display_name": display}

    body = {
        "displayName": display,
        # Align with common Outlook presets (see MailboxEnums.CategoryColor).
        "color": "preset4",
    }
    post_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=40.0) as client:
            res = client.post(base, headers=post_headers, json=body)
    except httpx.RequestError as e:
        raise RuntimeError(f"Could not reach Microsoft Graph: {e}") from e

    if res.status_code in (200, 201):
        return {"status": "created", "display_name": display}

    if res.status_code == 409:
        return {"status": "already_present", "display_name": display}

    txt = (res.text or "").strip()
    try:
        err = res.json()
        detail = err.get("error", {})
        code = detail.get("code") if isinstance(detail, dict) else None
        if code == "NameAlreadyExists" or res.status_code == 409:
            return {"status": "already_present", "display_name": display}
    except json.JSONDecodeError:
        pass

    raise RuntimeError(f"Graph create masterCategory failed ({res.status_code}): {txt[:1200]}")


def _graph_message_base_url(mailbox: str, message_id: str) -> str:
    """Single path segment for ``message_id`` (must be Graph REST id; encode ``/``, ``+``, etc.)."""
    mbox = mailbox.strip()
    mid = (message_id or "").strip()
    return f"https://graph.microsoft.com/v1.0/users/{quote(mbox)}/messages/{quote(mid, safe='')}"


def _pick_newest_graph_message_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_sent = ""
    for row in rows:
        if not isinstance(row, dict):
            continue
        sent = row.get("sentDateTime")
        sent_s = sent.strip() if isinstance(sent, str) else ""
        if best is None or sent_s > best_sent:
            best = row
            best_sent = sent_s
    return best


def _graph_messages_filter_request(
    url: str,
    filt: str,
    token: str,
    *,
    top: str = "15",
) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}"}
    params: dict[str, str] = {
        "$filter": filt,
        "$select": "id,webLink,sentDateTime",
        "$top": top,
    }
    try:
        with httpx.Client(timeout=45.0) as client:
            res = client.get(url, headers=headers, params=params)
    except httpx.RequestError:
        return []
    if res.status_code >= 400:
        return []
    try:
        data = res.json()
    except json.JSONDecodeError:
        return []
    vals = data.get("value") if isinstance(data, dict) else None
    if not isinstance(vals, list):
        return []
    return [x for x in vals if isinstance(x, dict)]


def _lookup_graph_message_id_by_conversation_id(
    mailbox: str,
    conversation_id: str,
    token: str,
) -> tuple[str | None, str | None]:
    """
    Resolve the newest Graph message in a thread (e.g. sent copy after compose capture).

    Returns ``(graph_message_id, webLink)`` or ``(None, None)``.
    """
    conv = (conversation_id or "").strip()
    if not conv:
        return (None, None)
    esc = conv.replace("'", "''")
    filt = f"conversationId eq '{esc}' and isDraft eq false"
    mbox = quote(mailbox.strip())
    base = f"https://graph.microsoft.com/v1.0/users/{mbox}"
    rows: list[dict[str, Any]] = []
    rows.extend(_graph_messages_filter_request(f"{base}/mailFolders/sentitems/messages", filt, token))
    if not rows:
        rows.extend(_graph_messages_filter_request(f"{base}/mailFolders/inbox/messages", filt, token))
    row = _pick_newest_graph_message_row(rows)
    if not row:
        return (None, None)
    gid = row.get("id") if isinstance(row.get("id"), str) else None
    wl = row.get("webLink") if isinstance(row.get("webLink"), str) else None
    gid_out = gid.strip() if gid and gid.strip() else None
    wl_out = None
    if wl and wl.strip().startswith(("http://", "https://")):
        wl_out = _normalize_outlook_office365_web_link_to_office_com(wl.strip())
    return (gid_out, wl_out)


def _lookup_graph_message_id_by_internet_message_id(mailbox: str, internet_message_id: str, token: str) -> str | None:
    """Resolve Graph ``id`` when GET by item id fails (OData ``$filter`` on ``internetMessageId``)."""
    imid = (internet_message_id or "").strip()
    if not imid:
        return None
    esc = imid.replace("'", "''")
    filt = f"internetMessageId eq '{esc}'"
    url = f"https://graph.microsoft.com/v1.0/users/{quote(mailbox.strip())}/messages"
    headers = {"Authorization": f"Bearer {token}"}
    params: dict[str, str] = {"$filter": filt, "$select": "id", "$top": "1"}
    try:
        with httpx.Client(timeout=45.0) as client:
            res = client.get(url, headers=headers, params=params)
    except httpx.RequestError:
        return None
    if res.status_code >= 400:
        return None
    try:
        data = res.json()
    except json.JSONDecodeError:
        return None
    vals = data.get("value") if isinstance(data, dict) else None
    if not isinstance(vals, list) or not vals:
        return None
    gid = vals[0].get("id") if isinstance(vals[0], dict) else None
    if isinstance(gid, str) and gid.strip():
        return gid.strip()
    return None


def _merge_categories_once(mailbox: str, message_id: str, display: str, token: str) -> dict[str, Any]:
    base = _graph_message_base_url(mailbox, message_id)
    headers = {"Authorization": f"Bearer {token}"}

    try:
        with httpx.Client(timeout=45.0) as client:
            res = client.get(f"{base}?$select=categories", headers=headers)
    except httpx.RequestError as e:
        raise RuntimeError(f"Could not reach Microsoft Graph: {e}") from e

    if res.status_code == 404:
        raise RuntimeError(
            "Graph could not find this message by id — try converting itemId with convertToRestId in the add-in, "
            "or rely on internet_message_id fallback.",
        )
    if res.status_code >= 400:
        txt = (res.text or "").strip()
        raise RuntimeError(f"Graph GET message failed ({res.status_code}): {txt[:900]}")

    try:
        data = res.json()
    except json.JSONDecodeError:
        raise RuntimeError("Graph returned non-JSON for GET message.") from None

    current = data.get("categories") if isinstance(data, dict) else None
    if not isinstance(current, list):
        current = []
    strs = [str(x) for x in current if isinstance(x, str) and str(x).strip()]
    if any(s.strip().lower() == display.lower() for s in strs):
        return {"status": "already_tagged", "display_name": display}

    merged = strs + [display]
    patch_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=45.0) as client:
            pres = client.patch(base, headers=patch_headers, json={"categories": merged})
    except httpx.RequestError as e:
        raise RuntimeError(f"Could not reach Microsoft Graph: {e}") from e

    if pres.status_code in (200, 204):
        return {"status": "tagged", "display_name": display}

    txt = (pres.text or "").strip()
    raise RuntimeError(f"Graph PATCH message categories failed ({pres.status_code}): {txt[:1200]}")


def _append_popout_v2_to_outlook_url(url: str) -> str:
    """Ensure ``popoutv2=1`` on OWA links so the reading pane opens in a separate window."""
    u = (url or "").strip()
    if not u:
        return u
    try:
        p = urlparse(u)
        pairs = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False) if k.lower() != "popoutv2"]
        pairs.append(("popoutv2", "1"))
        new_q = urlencode(pairs, doseq=True)
        return urlunparse((p.scheme, p.netloc, p.path, p.params, new_q, p.fragment))
    except Exception:
        return u


def resolve_outlook_owa_link_via_graph(
    mailbox: str,
    message_id: str,
    internet_message_id: str | None = None,
    *,
    db: Session,
) -> tuple[str | None, str | None]:
    """
    Fetch Microsoft Graph ``webLink`` for this message (canonical OWA open URL).

    Returns ``(owa_url, resolved_graph_id_or_none)``. When the stored id is stale but
    ``internet_message_id`` matches, the second value is the Graph ``id`` to persist.

    Requires application permissions that include reading the owner's mailbox (same as category tagging).
    """
    if not graph_mail_configured(db):
        return (None, None)

    mbox = mailbox.strip()
    mid_raw = (message_id or "").strip()
    if not mbox or not mid_raw:
        return (None, None)

    token = app_access_token(db)
    imid_opt = (internet_message_id or "").strip() or None

    def fetch_web_link(mid: str) -> str | None:
        base = _graph_message_base_url(mbox, mid)
        headers = {"Authorization": f"Bearer {token}"}
        try:
            with httpx.Client(timeout=25.0) as client:
                res = client.get(f"{base}?$select=webLink", headers=headers)
        except httpx.RequestError:
            return None
        if res.status_code >= 400:
            return None
        try:
            data = res.json()
        except json.JSONDecodeError:
            return None
        wl = data.get("webLink") if isinstance(data, dict) else None
        if isinstance(wl, str) and wl.strip().startswith(("http://", "https://")):
            norm = _normalize_outlook_office365_web_link_to_office_com(wl.strip())
            return norm
        return None

    wl = fetch_web_link(mid_raw)
    if wl:
        return (wl, None)

    if imid_opt:
        resolved = _lookup_graph_message_id_by_internet_message_id(mbox, imid_opt, token)
        if resolved and resolved != mid_raw:
            wl2 = fetch_web_link(resolved)
            if wl2:
                return (wl2, resolved)
    return (None, None)


def resolve_outlook_owa_link_via_conversation(
    mailbox: str,
    conversation_id: str,
    *,
    db: Session,
) -> tuple[str | None, str | None]:
    """Find the latest message in a thread and return ``(webLink, graph_message_id)``."""
    if not graph_mail_configured(db):
        return (None, None)
    mbox = mailbox.strip()
    conv = (conversation_id or "").strip()
    if not mbox or not conv:
        return (None, None)
    token = app_access_token(db)
    gid, wl = _lookup_graph_message_id_by_conversation_id(mbox, conv, token)
    if wl:
        return (wl, gid)
    if gid:
        return resolve_outlook_owa_link_via_graph(mbox, gid, None, db=db)
    return (None, None)


def merge_canary_category_on_message(
    mailbox: str,
    message_id: str,
    internet_message_id: str | None = None,
    *,
    db: Session,
) -> dict[str, Any]:
    """
    GET message ``categories``, merge in the configured Canary name, PATCH back.

    Pass a **Graph REST** message id (use Office.js ``convertToRestId(item.itemId, v2.0)``). Raw EWS-style
    ``itemId`` values often contain ``/`` and break OData URLs (``RequestBroker--ParseUri``).

    Optional ``internet_message_id`` enables a second attempt via ``$filter=internetMessageId eq …``.
    """
    if not graph_mail_configured(db):
        raise RuntimeError("Microsoft Graph is not configured (set CANARY_MS_GRAPH_*).")

    mbox = mailbox.strip()
    mid_raw = (message_id or "").strip()
    if not mbox or not mid_raw:
        raise RuntimeError("mailbox and message_id are required.")

    display = _primary_category_display_name()
    token = app_access_token(db)
    imid_opt = (internet_message_id or "").strip() or None

    try:
        return _merge_categories_once(mbox, mid_raw, display, token)
    except RuntimeError as first_err:
        err_txt = str(first_err)
        retry = imid_opt and (
            "ParseUri" in err_txt
            or "RequestBroker" in err_txt
            or "Graph GET message failed (400)" in err_txt
            or "Graph GET message failed (404)" in err_txt
        )
        if not retry:
            raise first_err from None
        resolved = _lookup_graph_message_id_by_internet_message_id(mbox, imid_opt, token)
        if not resolved or resolved == mid_raw:
            raise first_err from None
        return _merge_categories_once(mbox, resolved, display, token)
