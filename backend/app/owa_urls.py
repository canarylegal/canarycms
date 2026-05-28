"""Outlook on the web (OWA) URL helpers for opening filed messages."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, parse_qsl, quote, unquote, urlencode, urlparse

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


def owa_origin_for_compose_navigation(owa_base: str | None) -> tuple[str, str]:
    """OWA host for compose — always the configured base (must match the signed-in OWA session)."""
    return owa_origin_and_mail_prefix(owa_base)


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


def extract_item_id_from_graph_message_body(body: dict) -> str:
    """Exchange REST item id from Graph ``webLink`` query, else Graph message ``id``."""
    draft_id = body.get("id")
    if not isinstance(draft_id, str) or not draft_id.strip():
        raise ValueError("Graph message body did not include id.")
    web_link = body.get("webLink")
    if isinstance(web_link, str) and web_link.strip():
        from_web = extract_item_id_from_outlook_web_url(web_link)
        if from_web:
            return from_web
    return draft_id.strip()


def owa_compose_item_id_from_graph_body(body: dict) -> str:
    """Item id for OWA deeplinks — must be ``webLink`` ``ItemID`` (REST), not Graph ``id``."""
    return extract_item_id_from_graph_message_body(body)


def _compose_origin_prefix(_graph_body: dict, owa_base: str | None) -> tuple[str, str]:
    """
    OWA origin for opening a Graph draft in the browser.

    Always use the configured ``outlook_web_mail_base`` (e.g. ``outlook.cloud.microsoft``). Graph
    ``webLink`` hosts are often ``outlook.office.com`` / ``outlook.office365.com`` and open an empty
    compose window when the user is signed in on ``outlook.cloud.microsoft``.
    """
    return owa_origin_and_mail_prefix(owa_base)


def build_owa_compose_prefill_url(
    owa_base: str | None,
    *,
    to: str,
    subject: str,
    body: str,
    graph_body: dict | None = None,
) -> str:
    """Open a **new** OWA compose window with To/Subject/Body prefilled (no Graph draft item)."""
    if graph_body:
        origin, prefix = _compose_origin_prefix(graph_body, owa_base)
    else:
        origin, prefix = owa_origin_for_compose_navigation(owa_base)
    parts: list[str] = []
    to_clean = (to or "").strip()
    if to_clean:
        parts.append(f"to={quote(to_clean)}")
    parts.append(f"subject={quote(subject or '')}")
    parts.append(f"body={quote(body or '')}")
    return f"{origin}{prefix}/deeplink/compose?{'&'.join(parts)}&popoutv2=1"


def _compose_prefill_query_params(*, to: str, subject: str, body: str, max_body_len: int = 6000) -> str:
    """URL query fragment for To/Subject/Body (OWA compose deeplink)."""
    parts: list[str] = []
    to_clean = (to or "").strip()
    if to_clean:
        parts.append(f"to={quote(to_clean)}")
    parts.append(f"subject={quote((subject or '').strip())}")
    body_clean = (body or "").strip()
    if len(body_clean) > max_body_len:
        body_clean = body_clean[: max_body_len - 40] + "\n\n[Body truncated for URL length.]"
    parts.append(f"body={quote(body_clean)}")
    return "&".join(parts)


def _append_query(url: str, query_suffix: str) -> str:
    if not query_suffix:
        return url
    return f"{url}&{query_suffix}" if "?" in url else f"{url}?{query_suffix}"


def _encode_owa_compose_query(pairs: list[tuple[str, str]]) -> str:
    """Encode compose query with ``%20`` for spaces (not ``+``), matching the working prefill URLs."""
    return "&".join(f"{quote(k, safe='')}={quote(v, safe='')}" for k, v in pairs)


def _itemid_query_pairs_from_graph_weblink(graph_create_body: dict) -> list[tuple[str, str]]:
    """``ItemID`` / ``exvsurl`` from Graph ``webLink``, else REST id / Graph ``id`` from the message body."""
    item_id: str | None = None
    extras: list[tuple[str, str]] = []
    web_link = graph_create_body.get("webLink")
    if isinstance(web_link, str) and web_link.strip():
        try:
            pq = urlparse(web_link.strip())
            if pq.query:
                for k, v in parse_qsl(pq.query, keep_blank_values=False):
                    kl = k.lower()
                    if kl == "viewmodel":
                        continue
                    if kl == "itemid":
                        item_id = v
                        continue
                    if kl == "popoutv2":
                        continue
                    extras.append((k, v))
        except Exception:
            pass

    if not item_id:
        try:
            item_id = owa_compose_item_id_from_graph_body(graph_create_body)
        except ValueError:
            return []

    pairs: list[tuple[str, str]] = [("ItemID", item_id)]
    if not any(k.lower() == "exvsurl" for k, _ in extras):
        pairs.append(("exvsurl", "1"))
    pairs.extend(extras)
    pairs.append(("popoutv2", "1"))
    return pairs


def _compose_prefill_param_pairs(*, to: str, subject: str, body: str, max_body_len: int = 6000) -> list[tuple[str, str]]:
    """Unencoded name/value pairs for compose deeplinks (encoded once via ``_encode_owa_compose_query``)."""
    pairs: list[tuple[str, str]] = []
    to_clean = (to or "").strip()
    if to_clean:
        pairs.append(("to", to_clean))
    pairs.append(("subject", (subject or "").strip()))
    body_clean = (body or "").strip()
    if len(body_clean) > max_body_len:
        body_clean = body_clean[: max_body_len - 40] + "\n\n[Body truncated for URL length.]"
    pairs.append(("body", body_clean))
    return pairs


def _merge_itemid_and_prefill_compose_pairs(
    item_pairs: list[tuple[str, str]],
    *,
    to: str,
    subject: str,
    body: str,
) -> list[tuple[str, str]]:
    """Merge Graph ``ItemID`` params with prefill; encode once with ``quote`` (``%20``, not ``+``)."""
    reserved = {k.lower() for k, _ in item_pairs}
    merged: list[tuple[str, str]] = list(item_pairs)
    for key, val in _compose_prefill_param_pairs(to=to, subject=subject, body=body):
        if key.lower() not in reserved:
            merged.append((key, val))
            reserved.add(key.lower())
    merged = [(k, v) for k, v in merged if k.lower() != "popoutv2"]
    merged.append(("popoutv2", "1"))
    return merged


def build_owa_compose_deeplink_from_graph_weblink(
    graph_create_body: dict,
    owa_base: str | None,
    *,
    to: str = "",
    subject: str = "",
    body: str = "",
) -> str:
    """ItemID-only compose on ``/mail/deeplink`` (backup / Drafts link)."""
    item_pairs = _itemid_query_pairs_from_graph_weblink(graph_create_body)
    if item_pairs:
        origin, _prefix = _compose_origin_prefix(graph_create_body, owa_base)
        _ = (to, subject, body)
        return f"{origin}/mail/deeplink/compose?{_encode_owa_compose_query(item_pairs)}"

    _path_primary, query_fallback = build_owa_open_graph_draft_compose_urls(graph_create_body, owa_base)
    base = query_fallback or _path_primary
    prefill_extra = _compose_prefill_query_params(to=to, subject=subject, body=body)
    return _append_query(base, prefill_extra) if prefill_extra else base


def build_owa_compose_with_graph_attachments(
    graph_create_body: dict,
    owa_base: str | None,
    *,
    to: str,
    subject: str,
    body: str,
) -> str:
    """
    Compose URL when the message has Graph-stored attachments.

    Uses the same ``/mail/0/deeplink/compose`` route as prefill, plus ``ItemID`` so OWA can bind
    the open draft (files on the Graph message). Prefill params use ``%20`` encoding (not ``+``).
    """
    item_pairs = _itemid_query_pairs_from_graph_weblink(graph_create_body)
    if not item_pairs:
        return build_owa_compose_prefill_url(owa_base, to=to, subject=subject, body=body)
    origin, prefix = _compose_origin_prefix(graph_create_body, owa_base)
    merged = _merge_itemid_and_prefill_compose_pairs(
        item_pairs,
        to=to,
        subject=subject,
        body=body,
    )
    return f"{origin}{prefix}/deeplink/compose?{_encode_owa_compose_query(merged)}"


def build_owa_open_graph_draft_compose_urls(
    graph_create_body: dict,
    owa_base: str | None,
) -> tuple[str, str]:
    """
    Open a Graph-created draft in OWA (attachments + merged body live on the draft).

    Returns ``(path_style, query_style)`` on ``/mail/0/…``. Prefer query-style via
    ``build_owa_compose_deeplink_from_graph_weblink`` for opening drafts in compose mode.
    """
    rest_id = owa_compose_item_id_from_graph_body(graph_create_body)
    enc_rest = quote(rest_id, safe="")
    origin, prefix = _compose_origin_prefix(graph_create_body, owa_base)
    path_style = f"{origin}{prefix}/deeplink/compose/{enc_rest}?ItemID={enc_rest}&exvsurl=1&popoutv2=1"
    query_style = f"{origin}{prefix}/deeplink/compose?ItemID={enc_rest}&exvsurl=1&popoutv2=1"
    graph_id = graph_create_body.get("id")
    if isinstance(graph_id, str) and graph_id.strip() and graph_id.strip() != rest_id:
        enc_gid = quote(graph_id.strip(), safe="")
        query_style = (
            f"{origin}{prefix}/deeplink/compose?ItemID={enc_gid}&exvsurl=1&popoutv2=1"
        )
    return path_style, query_style


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
