"""Outlook on the web (OWA) URL helpers for opening filed messages."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, quote, unquote, urlparse

from app.email_integration_settings import effective_outlook_web_mail_base

DEFAULT_OWA_MAIL = "https://outlook.office.com/mail"
OUTLOOK_GRAPH_MESSAGE_ID_MAX = 450


def outlook_graph_message_id_storable(rest_id: str | None) -> str | None:
    """Return a value safe for ``outlook_graph_message_id`` (VARCHAR 450); long ids stay in ``source_outlook_item_id`` only."""
    t = (rest_id or "").strip()
    if not t or len(t) > OUTLOOK_GRAPH_MESSAGE_ID_MAX:
        return None
    return t


def normalize_owa_host(url: str) -> str:
    """Map ``outlook.office365.com`` to ``outlook.office.com`` (Graph / OWA convention)."""
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


def owa_origin_and_mail_prefix(owa_base: str | None) -> tuple[str, str]:
    """
    Derive OWA origin and path prefix from a user or org base URL
    (e.g. ``https://outlook.office.com/mail`` → origin + ``/mail/0``).
    """
    raw = (owa_base or "").strip() or DEFAULT_OWA_MAIL
    try:
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        host_url = normalize_owa_host(f"{parsed.scheme}://{parsed.netloc}")
        path = (parsed.path or "").lower()
        if "/mail/0" in path:
            prefix = "/mail/0"
        else:
            prefix = "/mail/0"
        return host_url.rstrip("/"), prefix
    except Exception:
        return "https://outlook.office.com", "/mail/0"


def looks_like_exchange_item_id(item_id: str | None) -> bool:
    iid = (item_id or "").strip()
    if not iid or "[object" in iid.lower():
        return False
    if iid.startswith(("AAMk", "AQMk", "AQAA")):
        return True
    if "@" in iid:
        return False
    return len(iid) >= 40


def extract_item_id_from_outlook_web_url(url: str | None) -> str | None:
    trimmed = (url or "").strip()
    if not trimmed:
        return None
    try:
        u = urlparse(trimmed if "://" in trimmed else f"https://{trimmed}")
        pairs = parse_qs(u.query, keep_blank_values=False)
        for k, vals in pairs.items():
            if k.lower() == "itemid" and vals and vals[0].strip():
                return vals[0].strip()
        read_path = re.search(r"/deeplink/read/([^/?]+)", u.path, re.I)
        if read_path:
            return unquote(read_path.group(1)).strip()
    except Exception:
        pass
    return None


def is_canary_synthetic_message_id(message_id: str | None) -> bool:
    return "@canary-outlook-addin" in (message_id or "").strip().lower()


def is_usable_outlook_message_web_link(url: str | None) -> bool:
    """True when ``url`` looks like a Graph/OWA open link for a single message."""
    trimmed = (url or "").strip()
    if not trimmed.startswith(("http://", "https://")):
        return False
    low = trimmed.lower()
    if "deeplink/search" in low:
        return False
    if "deeplink/read" in low:
        return True
    if "itemid=" in low:
        return True
    if "/owa/" in low and "viewmodel=readmessageitem" in low:
        return True
    return False


def owa_origin_and_mail_prefix_for_item_id(
    owa_base: str | None,
    outlook_web_link: str | None,
) -> tuple[str, str]:
    """Prefer the OWA host from a stored Graph ``webLink`` (tenant ``outlook.cloud.microsoft`` vs ``office.com``)."""
    wl = (outlook_web_link or "").strip()
    if wl:
        try:
            parsed = urlparse(wl if "://" in wl else f"https://{wl}")
            if parsed.netloc:
                host_url = normalize_owa_host(f"{parsed.scheme}://{parsed.netloc}")
                return host_url.rstrip("/"), "/mail/0"
        except Exception:
            pass
    return owa_origin_and_mail_prefix(owa_base)


def build_owa_read_message_url(
    item_id: str,
    owa_base: str | None = None,
    *,
    outlook_web_link: str | None = None,
) -> str | None:
    """
    Build an OWA read URL for a Graph / REST message id.

    Uses the tenant host from ``outlook_web_link`` when present (Graph ``webLink`` host must match).
    """
    iid = (item_id or "").strip()
    if not looks_like_exchange_item_id(iid):
        return None
    origin, prefix = owa_origin_and_mail_prefix_for_item_id(owa_base, outlook_web_link)
    enc = quote(iid, safe="")
    return (
        f"{origin}{prefix}/deeplink/read/{enc}"
        f"?ItemID={enc}&exvsurl=1&viewmodel=ReadMessageItem"
    )


def resolve_owa_read_url_for_file(
    *,
    outlook_graph_message_id: str | None,
    source_outlook_item_id: str | None,
    outlook_web_link: str | None,
    source_internet_message_id: str | None,
    owa_base: str | None,
) -> str | None:
    """Best-effort OWA read URL for a filed parent .eml, or ``None`` if not openable in OWA."""
    _ = source_internet_message_id  # synthetic Message-ID does not block when REST item ids exist
    wl = (outlook_web_link or "").strip()
    if is_usable_outlook_message_web_link(wl):
        return wl
    for candidate in (
        source_outlook_item_id,
        outlook_graph_message_id,
        extract_item_id_from_outlook_web_url(outlook_web_link),
    ):
        if candidate and looks_like_exchange_item_id(candidate):
            built = build_owa_read_message_url(
                candidate,
                owa_base,
                outlook_web_link=outlook_web_link,
            )
            if built:
                return built
    return None


def effective_owa_base_for_open(owa_base_query: str | None, db) -> str:
    q = (owa_base_query or "").strip()
    if q:
        return q.rstrip("/")
    return effective_outlook_web_mail_base(db)
